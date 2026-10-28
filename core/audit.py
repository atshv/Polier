"""The compliance view of the board: does every task carry the evidence its status claims?

``audit`` compares the plan state (``board.json``) with the execution state
(``runs/<ID>.json``) and the evidence on disk (``reviews/``, gate records):
attempts against the policy limit, every gate against its passing record, the
review verdict, the handoff, the run record and the approvals a dependency
manifest needs. ``audit_task`` does one task, ``audit`` the whole board.

Severity follows the status: for a ``done`` task an enabled check is an
**error** (it claims a finished task without the proof); for every other status
a finding is a **warning**. Without ``policy.json`` the policy-driven checks are
not enforced, so a missing gate/review/handoff/run record is a warning, never an
error — a 1.0 project stays green.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from . import approvals, evidence, runs
from .board import load_board, tasks_of
from .errors import PolierError
from .policy import (DEFAULTS, checks as policy_checks, enabled as policy_enabled,
                     limits as policy_limits, load_policy, manifest_match)

REVIEW = Path("reviews")
VERDICT = re.compile(r"(?im)^[\s>*-]*verdict\s*:\s*([A-Za-z_-]+)")
ACTIVE = ("claimed", "in_progress", "verifying", "review", "rework")


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _attempts(root, task_id: str) -> int:
    """Attempts used; a run record the store cannot name counts as 0."""
    try:
        return runs.attempt_count(root, task_id)
    except PolierError:
        return 0


def _review(root, task_id: str) -> dict:
    """The review file of a task: project-relative path, presence and verdict."""
    path = Path(root) / REVIEW / f"{task_id}.md"
    verdict = None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = ""
    if text:
        match = VERDICT.search(text)
        if match:
            verdict = match.group(1).lower()
    return {"file": f"reviews/{task_id}.md", "present": path.is_file(), "verdict": verdict}


def _review_problem(root, task_id: str) -> Optional[str]:
    review = _review(root, task_id)
    if not review["present"]:
        return f"review file reviews/{task_id}.md is missing"
    if review["verdict"] is None:
        return f"reviews/{task_id}.md has no 'verdict:' line"
    if review["verdict"] != "pass":
        return f"reviews/{task_id}.md says verdict: {review['verdict']} (needs verdict: pass)"
    return None


def _handoff_problem(task: dict) -> Optional[str]:
    handoff = task.get("handoff")
    if not isinstance(handoff, list) or not handoff:
        return "no handoff for the dependent tasks"
    if len(handoff) > 3:
        return f"handoff has {len(handoff)} lines (max. 3)"
    if any(not isinstance(line, str) or not line.strip() for line in handoff):
        return "handoff lines must be non-empty strings"
    return None


def _dependents(board: dict, task_id: str) -> List[str]:
    return [str(task.get("id")) for task in tasks_of(board)
            if isinstance(task.get("depends_on"), list) and task_id in task["depends_on"]]


def _dependency_manifest(policy, task: dict) -> Optional[str]:
    """The manifest a ``scope_write`` entry touches, when dependency approval is on."""
    if not policy_enabled(policy):
        return None
    dependencies = policy.get("dependencies")
    dependencies = dependencies if isinstance(dependencies, dict) else {}
    if not dependencies.get("approval", DEFAULTS["dependencies"]["approval"]):
        return None
    for entry in task.get("scope_write") or []:
        if not isinstance(entry, str) or not entry.strip():
            continue
        matched = manifest_match(policy, entry)
        if matched:
            return matched
    return None


def _approval_actions(policy) -> List[str]:
    raw = policy.get("approvals") if isinstance(policy, dict) else None
    actions = raw.get("actions") if isinstance(raw, dict) else None
    if not isinstance(actions, list):
        actions = DEFAULTS["approvals"]["actions"]
    return [action for action in actions if isinstance(action, str)]


def _approvals_for(root, task_id: str, policy) -> List[dict]:
    """Per action: the granted record, else the pending one, else none.

    With a policy every action it lists is reported, so the block shows which
    approvals this task still needs. Without a policy only the records that
    concern the task are listed (approvals are not required then).
    """
    out: List[dict] = []
    policy_on = policy_enabled(policy)
    actions = _approval_actions(policy) if policy_on else []
    seen = set()
    for action in actions:
        granted = approvals.granted(root, action, task_id)
        if granted is not None:
            out.append({"action": action, "status": "granted", "id": granted.get("id")})
            seen.add(action)
            continue
        pending = [record for record in approvals.pending(root, task_id)
                   if record.get("action") == action]
        if pending:
            out.append({"action": action, "status": "pending", "id": pending[0].get("id")})
        else:
            out.append({"action": action, "status": "none", "id": None})
        seen.add(action)
    if not policy_on:
        for record in approvals.load_all(root):
            if record.get("status") not in ("granted", "pending"):
                continue
            if record.get("task") not in (None, task_id):
                continue
            if record.get("action") in seen:
                continue
            out.append({"action": record.get("action"), "status": record.get("status"),
                        "id": record.get("id")})
    return out


def _findings(root, board: dict, task: dict, policy) -> List[dict]:
    """Every problem of one task, with the severity its status allows."""
    task_id = str(task.get("id"))
    status = task.get("status")
    done = status == "done"
    policy_on = policy_enabled(policy)
    flags = policy_checks(policy)
    limits = policy_limits(policy)
    max_attempts = limits["max_attempts_per_task"]
    attempts = _attempts(root, task_id)
    findings: List[dict] = []

    def add(check: str, message: str, hard: bool) -> None:
        findings.append({"check": check, "severity": "error" if hard else "warning",
                         "message": message})

    # -- attempts: a done task over the limit breaks the policy record ---------
    if attempts > max_attempts:
        add("attempts",
            f"{task_id}: attempts {attempts}/{max_attempts} used — over the limit",
            done and policy_on)

    # -- gates: the proof of every gate the task lists -------------------------
    gates = [gate for gate in task.get("gates") or [] if isinstance(gate, str) and gate.strip()]
    passed = evidence.passing_gates(root, task_id)
    missing = [gate for gate in gates if gate not in passed]
    if missing:
        names = ", ".join(missing)
        if done:
            suffix = "" if policy_on else " (no policy.json: not enforced)"
            add("gates", f"{task_id}: no passing gate record for {names}{suffix}", policy_on)
        elif status == "review" and policy_on:
            add("gates", f"{task_id}: no passing gate record for {names}", False)

    # -- review verdict --------------------------------------------------------
    if flags["review_before_done"]:
        problem = _review_problem(root, task_id) if done else None
        if problem:
            suffix = "" if policy_on else " (no policy.json: not enforced)"
            add("review", f"{task_id}: {problem}{suffix}", policy_on)
        elif status == "review" and policy_on:
            review = _review(root, task_id)
            if review["present"] and review["verdict"] not in (None, "pass"):
                add("review", f"{task_id}: reviews/{task_id}.md says verdict: "
                              f"{review['verdict']} (needs verdict: pass)", False)

    # -- handoff for the tasks that depend on this one -------------------------
    dependents = _dependents(board, task_id)
    if flags["handoff_before_done"] and dependents:
        problem = _handoff_problem(task)
        if problem and done:
            suffix = "" if policy_on else " (no policy.json: not enforced)"
            add("handoff",
                f"{task_id}: {problem} (depended on by {', '.join(dependents)}){suffix}",
                policy_on)
        elif problem and status == "review" and policy_on:
            add("handoff",
                f"{task_id}: {problem} (depended on by {', '.join(dependents)})", False)

    # -- the run record --------------------------------------------------------
    if flags["run_record"]:
        try:
            present = runs.run_path(root, task_id).is_file()
        except PolierError:
            present = False
        if done and not present:
            suffix = "" if policy_on else " (no policy.json: not enforced)"
            add("run_record", f"{task_id}: no run record runs/{task_id}.json{suffix}", policy_on)
        elif status in ("in_progress", "verifying", "review") and policy_on and not present:
            add("run_record", f"{task_id}: no run record runs/{task_id}.json for a "
                              f"{status} task", False)

    # -- dependency approval ---------------------------------------------------
    manifest = _dependency_manifest(policy, task)
    if manifest and not approvals.has_grant(root, "new_dependency", task_id):
        message = (f"{task_id}: scope_write touches dependency manifest {manifest!r} "
                   "without a granted new_dependency approval")
        if done:
            add("new_dependency", message, True)
        elif status in ACTIVE:
            add("new_dependency", message, False)

    return findings


def audit_task(root, board, task, policy) -> dict:
    """The compliance view of one task: its state, evidence, approvals and findings.

    ``task`` is a board task or a task id. For a ``done`` task an enabled check
    that fails is an error, for every other status it is a warning.
    """
    root = Path(root)
    board = board if isinstance(board, dict) else {}
    policy = policy if isinstance(policy, dict) else {"enabled": False}
    if isinstance(task, str):
        task_id = task
        entry = next((item for item in tasks_of(board) if item.get("id") == task_id), None)
        if entry is None:
            raise PolierError(f"task {task_id} is not on the board")
    elif isinstance(task, dict):
        entry = task
        task_id = entry.get("id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise PolierError("audit_task needs a task id")
    else:
        raise PolierError("audit_task needs a board task or a task id")

    limits = policy_limits(policy)
    gates = [gate for gate in entry.get("gates") or [] if isinstance(gate, str)]
    passed = evidence.passing_gates(root, task_id)
    try:
        run_record = runs.run_path(root, task_id).is_file()
    except PolierError:
        run_record = False
    findings = _findings(root, board, entry, policy)
    record = {
        "task": task_id,
        "title": entry.get("title"),
        "status": entry.get("status"),
        "attempts": _attempts(root, task_id),
        "max_attempts": limits["max_attempts_per_task"],
        "gates": gates,
        "passed": sorted(passed),
        "missing_gates": [gate for gate in gates if gate not in passed],
        "review": _review(root, task_id),
        "handoff": [line for line in entry.get("handoff") or [] if isinstance(line, str)],
        "approvals": _approvals_for(root, task_id, policy),
        "run_record": run_record,
        "dependency_manifest": _dependency_manifest(policy, entry),
        "findings": findings,
        "errors": [finding["message"] for finding in findings
                   if finding["severity"] == "error"],
        "warnings": [finding["message"] for finding in findings
                     if finding["severity"] == "warning"],
    }
    return record


def audit(root, board=None, policy=None) -> dict:
    """The compliance view of the whole board: ``{"tasks", "errors", "warnings"}``.

    ``board`` and ``policy`` may be passed in; by default they are loaded from
    ``root``. A broken ``policy.json`` is reported as a warning and treated as
    absent, so the audit itself never fails because of it.
    """
    root = Path(root)
    if board is None:
        board = load_board(root, strict=False)
        if board is None:
            raise PolierError(f"board.json not found in {root}")
    if not isinstance(board, dict):
        raise PolierError("board.json has no task list")
    warnings: List[str] = []
    if policy is None:
        try:
            policy = load_policy(root)
        except PolierError as exc:
            policy = {"enabled": False}
            warnings.append(f"policy.json cannot be used ({exc}); "
                            "policy checks are not enforced")
    tasks: List[dict] = []
    errors: List[str] = []
    for task in tasks_of(board):
        if not isinstance(task.get("id"), str):
            continue
        record = audit_task(root, board, task, policy)
        tasks.append(record)
        errors.extend(record["errors"])
        warnings.extend(record["warnings"])
    return {"tasks": tasks, "errors": errors, "warnings": warnings}
