"""The task state machine and its checkpoints (1.1).

``board.json`` stays the plan state; ``runs/<ID>.json`` is the execution state
(attempts, events); ``reviews/approvals`` holds the human decisions. A task
status changes only through :func:`set_status`: it checks the transition table
and the preconditions of the target, writes the board atomically under
``board.json.lock`` and records the side effects (attempt open/close, round
increment, events) in the run record.

Without ``policy.json`` the policy-driven checkpoints (attempt and concurrency
limits, gates, review verdict, handoff, run record, dependency approval) are
not enforced; they are reported as warnings instead, so a 1.0 project cannot
fail because 1.1 is new. The transition table, the note requirements and the
approvals that guard a done task or a forced change always apply.

A refused transition raises :class:`TransitionBlocked`, a PolierError subclass
whose ``.errors`` names every blocker and whose ``.actions`` carries the CLI
hint per blocker (``tools/state.py``, ``tools/approve.py``, ``tools/gate.py``).
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import evidence
from .approvals import has_grant, load_all, pending as pending_approvals
from .board import (BOARD, load_board, stage_report, task_stage_id, tasks_of)
from .errors import PolierError
from .policy import (DEFAULTS, checks as policy_checks, enabled as policy_enabled,
                     limits as policy_limits, load_policy, manifest_match)
from .runs import (FileLock, append_event, attempt_count, finish_attempt, load_run,
                   run_path, run_state, start_attempt)

TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "pending": ("claimed", "in_progress", "blocked", "failed"),
    "claimed": ("pending", "in_progress", "blocked", "failed"),
    "in_progress": ("verifying", "blocked", "failed"),
    "verifying": ("review", "rework", "blocked", "failed"),
    "review": ("done", "rework", "blocked", "failed"),
    "rework": ("in_progress", "blocked", "failed"),
    "blocked": ("pending", "in_progress", "failed"),
    "failed": ("pending", "in_progress"),
    "done": ("rework",),
}
STATUSES = tuple(TRANSITIONS)
NOTE_REQUIRED = ("rework", "blocked", "failed")
NEXT_STATUS = {
    "pending": "claimed",
    "claimed": "in_progress",
    "in_progress": "verifying",
    "verifying": "review",
    "review": "done",
    "rework": "in_progress",
    "blocked": "in_progress",
    "failed": "in_progress",
    "done": None,
}
REVIEW = Path("reviews")
VERDICT = re.compile(r"(?im)^[\s>*-]*verdict\s*:\s*([A-Za-z_-]+)")


class TransitionBlocked(PolierError):
    """A checkpoint refused the transition; `.errors` and `.actions` explain it."""

    def __init__(self, result: dict):
        self.result = dict(result or {})
        self.errors = list(self.result.get("errors") or [])
        self.actions = list(self.result.get("actions") or [])
        self.warnings = list(self.result.get("warnings") or [])
        self.requires = list(self.result.get("requires") or [])
        super().__init__("\n".join(self.errors) or "transition blocked")


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _int(value) -> int:
    return value if _is_int(value) else 0


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _unique(items) -> List:
    out: List = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def _unique_actions(actions: List[dict]) -> List[dict]:
    out: List[dict] = []
    seen = set()
    for action in actions:
        key = (action.get("action"), action.get("command"))
        if key in seen:
            continue
        seen.add(key)
        out.append(action)
    return out


def _state_hint(task_id: str, status: str) -> str:
    return f"python3 tools/state.py set {task_id} {status}"


def _request_hint(action: str, task_id: Optional[str] = None) -> str:
    command = f"python3 tools/approve.py request --action {action}"
    if task_id:
        command += f" --task {task_id}"
    return command + ' --note "..."'


def _action(code: str, command: str, reason: str) -> dict:
    return {"action": code, "command": command, "reason": reason}


def _policy(root) -> Tuple[dict, Optional[str]]:
    """(policy, warning): a broken policy is reported, then treated as absent."""
    try:
        return load_policy(root), None
    except PolierError as exc:
        return ({"enabled": False},
                f"policy.json cannot be used ({exc}); policy checkpoints are not enforced")


def _review_verdict(root, task_id: str) -> Optional[str]:
    path = Path(root) / REVIEW / f"{task_id}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = VERDICT.search(text)
    return match.group(1).lower() if match else None


def _review_problem(root, task_id: str) -> Optional[str]:
    path = Path(root) / REVIEW / f"{task_id}.md"
    if not path.is_file():
        return f"review file reviews/{task_id}.md is missing"
    verdict = _review_verdict(root, task_id)
    if verdict is None:
        return f"reviews/{task_id}.md has no 'verdict:' line"
    if verdict != "pass":
        return f"reviews/{task_id}.md says verdict: {verdict} (needs verdict: pass)"
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


def _stage_entry(root, board, task: dict) -> Tuple[Optional[str], Optional[dict]]:
    if not isinstance(board, dict) or not board.get("stages"):
        return None, None
    sid = task_stage_id(board, task)
    if not sid:
        return None, None
    for entry in stage_report(board, root):
        if entry.get("id") == sid:
            return sid, entry
    return sid, None


def _dependency_manifest(policy, task: dict) -> Optional[str]:
    """The manifest a scope_write entry touches, when dependency approval is on."""
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


# ---------------------------------------------------------------------------
# the transition check (no writes)
# ---------------------------------------------------------------------------

def check_transition(root, board, task, new_status, *, actor: str = "lead",
                     note=None, force: bool = False) -> dict:
    """Evaluate one transition without writing anything.

    Returns ``{"ok", "errors", "warnings", "requires", "actions", "task",
    "from", "to", "forced", "policy", "attempts", "max_attempts", "round"}``.
    `task` is a board task or a task ID; `force` needs a granted
    ``state_override`` approval and turns the forceable blockers into warnings.
    """
    root = Path(root)
    result: dict = {
        "ok": False, "errors": [], "warnings": [], "requires": [], "actions": [],
        "task": None, "from": None, "to": new_status, "forced": [], "policy": False,
        "attempts": 0, "max_attempts": None, "round": 0,
    }
    if board is None or not isinstance(board, dict):
        board = load_board(root, strict=False) or {}
    tasks = tasks_of(board)
    hard: List[str] = []
    pre: List[str] = []
    actions: List[dict] = result["actions"]
    requires: List[str] = result["requires"]

    def need(code: str, command: str, reason: str) -> None:
        actions.append(_action(code, command, reason))

    def req(name: str) -> None:
        requires.append(name)

    def finish() -> dict:
        result["errors"] = _unique(hard)
        result["warnings"] = _unique(result["warnings"])
        result["requires"] = _unique(requires)
        result["actions"] = _unique_actions(actions)
        result["ok"] = not result["errors"]
        return result

    # -- task and status ---------------------------------------------------
    entry = None
    task_id = None
    if isinstance(task, dict):
        entry = task
        task_id = task.get("id")
    elif isinstance(task, str) and task.strip():
        task_id = task.strip()
        entry = next((item for item in tasks if item.get("id") == task_id), None)
    if not isinstance(task_id, str) or not task_id.strip():
        hard.append("a state change needs a task id")
        return finish()
    task_id = task_id.strip()
    result["task"] = task_id
    if entry is None:
        hard.append(f"task {task_id} is not on the board")
        return finish()

    policy, policy_warning = _policy(root)
    policy_on = policy_enabled(policy)
    result["policy"] = policy_on
    if policy_warning:
        result["warnings"].append(policy_warning)
    limits = policy_limits(policy)
    result["max_attempts"] = limits["max_attempts_per_task"]
    result["attempts"] = attempt_count(root, task_id)
    result["round"] = _int(entry.get("round"))

    if new_status not in TRANSITIONS:
        hard.append(f"unknown status {new_status!r} (known: {', '.join(STATUSES)})")
        return finish()
    current = entry.get("status")
    result["from"] = current
    if current not in TRANSITIONS:
        hard.append(f"{task_id}: the board status {current!r} is unknown")
        return finish()
    allowed = TRANSITIONS[current]
    if new_status not in allowed:
        hard.append(
            f"{task_id}: transition {current} → {new_status} is not allowed "
            f"(from {current}: {', '.join(allowed) or 'nothing'})")
        for target in allowed:
            need("state", _state_hint(task_id, target),
                 f"allowed transition {current} → {target}")
        return finish()

    # -- checkpoints for every target -------------------------------------
    sid, stage = _stage_entry(root, board, entry)
    if stage is not None and stage.get("stopped"):
        hard.append(f"{task_id}: stage {sid} is stopped by the owner — do not work there")
        need("owner", f"python3 tools/state.py show {task_id} --json",
             f"the owner stopped stage {sid}")

    if current == "done" and not has_grant(root, "reopen_done", task_id):
        hard.append(f"{task_id}: changing a done task needs a granted reopen_done approval")
        req("reopen_done")
        need("reopen_done", _request_hint("reopen_done", task_id),
             "request the reopen; the owner grants it with "
             f"python3 tools/approve.py grant <ID> --by {DEFAULTS['approvals']['approver']}")

    if new_status in NOTE_REQUIRED and not _text(note):
        pre.append(f"{task_id}: a note is required for {new_status} "
                   f"(the reason and what is needed)")
        req("note")
        need("note", _state_hint(task_id, new_status) + ' --note "..."',
             f"repeat the change with a note for {new_status}")

    # -- target preconditions ---------------------------------------------
    if new_status == "in_progress":
        if policy_on:
            used = result["attempts"]
            attempt_limit = limits["max_attempts_per_task"]
            if used >= attempt_limit:
                pre.append(f"{task_id}: attempts {used}/{attempt_limit} used — escalate, do not retry")
                req("state_override")
                if "blocked" in allowed:
                    need("escalate", _state_hint(task_id, "blocked") + ' --note "..."',
                         f"attempts {used}/{attempt_limit} used; mark the task blocked and "
                         "escalate to the owner")
                else:
                    need("escalate", f"python3 tools/state.py show {task_id} --json",
                         f"attempts {used}/{attempt_limit} used; report the escalation to the owner")
                need("state_override", _request_hint("state_override", task_id),
                     "only to retry beyond the attempt limit anyway")
            running = [item.get("id") for item in tasks
                       if isinstance(item, dict) and item.get("status") == "in_progress"
                       and item.get("id") != task_id]
            concurrency = limits["max_in_progress"]
            if len(running) >= concurrency:
                names = ", ".join(str(item) for item in running)
                pre.append(f"{task_id}: {len(running)} task(s) already in_progress "
                           f"(max {concurrency}: {names})")
                req("max_in_progress")
                need("wait", "python3 tools/state.py show --json",
                     f"wait until one of {names} leaves in_progress")
        if stage is not None and stage.get("incomplete_deps"):
            waiting = ", ".join(stage["incomplete_deps"])
            pre.append(f"{task_id}: stage {sid} needs stage(s) {waiting} complete first")
            req("stage")
            need("wait", "python3 tools/dispatch.py --json",
                 f"stage {sid} waits for {waiting}")

    elif new_status == "verifying":
        record = load_run(root, task_id)
        open_attempt = any(item.get("ended") is None for item in record["attempts"])
        if not open_attempt:
            pre.append(f"{task_id}: no open attempt in runs/{task_id}.json — nothing to verify")
            req("attempt")
            need("state", _state_hint(task_id, "rework") + ' --note "..."',
                 "close the round, then start a new attempt through in_progress")
            need("state", _state_hint(task_id, "in_progress"),
                 "after rework, start the next attempt")

    elif new_status == "rework":
        if policy_on:
            round_limit = limits["max_review_rounds"]
            next_round = _int(entry.get("round")) + 1
            if next_round > round_limit:
                pre.append(f"{task_id}: round {next_round} would exceed "
                           f"max_review_rounds {round_limit} — escalate")
                req("state_override")
                if "blocked" in allowed:
                    need("escalate", _state_hint(task_id, "blocked") + ' --note "..."',
                         f"round {next_round}/{round_limit} reached; mark the task blocked "
                         "and escalate to the owner")
                else:
                    need("escalate", f"python3 tools/state.py show {task_id} --json",
                         f"round {next_round}/{round_limit} reached; report the escalation")
                need("state_override", _request_hint("state_override", task_id),
                     "only to continue beyond the review round limit")

    elif new_status == "review":
        _check_gates(root, entry, task_id, policy_on, pre, result["warnings"], req, need)

    elif new_status == "done":
        _check_gates(root, entry, task_id, policy_on, pre, result["warnings"], req, need)
        flags = policy_checks(policy)
        dependents = [str(item.get("id")) for item in tasks
                      if isinstance(item, dict) and task_id in (item.get("depends_on") or [])]
        if policy_on:
            if flags["review_before_done"]:
                problem = _review_problem(root, task_id)
                if problem:
                    pre.append(f"{task_id}: {problem}")
                    req("review")
                    need("review", f"reviews/{task_id}.md",
                         "the review must contain 'verdict: pass'")
            if flags["handoff_before_done"] and dependents:
                problem = _handoff_problem(entry)
                if problem:
                    pre.append(f"{task_id}: {problem} "
                               f"(depended on by {', '.join(dependents)})")
                    req("handoff")
                    need("handoff", f"board.json: task {task_id}, field handoff",
                         "add 1–3 handoff lines for the dependent tasks")
            if flags["run_record"] and not run_path(root, task_id).is_file():
                pre.append(f"{task_id}: no run record runs/{task_id}.json")
                req("run_record")
                need("run_record", f"runs/{task_id}.json",
                     "a run record is started by the transition to in_progress")
            manifest = _dependency_manifest(policy, entry)
            if manifest and not has_grant(root, "new_dependency", task_id):
                pre.append(f"{task_id}: scope_write touches dependency manifest {manifest!r} "
                           "without a granted new_dependency approval")
                req("new_dependency")
                need("new_dependency", _request_hint("new_dependency", task_id),
                     "the owner grants it with python3 tools/approve.py grant <ID> --by owner")
        else:
            if flags["review_before_done"]:
                problem = _review_problem(root, task_id)
                if problem:
                    result["warnings"].append(
                        f"{task_id}: {problem} (no policy.json: not enforced)")
            if flags["handoff_before_done"] and dependents:
                problem = _handoff_problem(entry)
                if problem:
                    result["warnings"].append(
                        f"{task_id}: {problem} (no policy.json: not enforced)")
            if flags["run_record"] and not run_path(root, task_id).is_file():
                result["warnings"].append(
                    f"{task_id}: no run record runs/{task_id}.json "
                    "(no policy.json: not enforced)")

    # -- force -------------------------------------------------------------
    if force:
        if has_grant(root, "state_override", task_id):
            if pre:
                result["forced"] = list(pre)
                for message in pre:
                    result["warnings"].append("forced: " + message)
        else:
            hard.extend(pre)
            hard.append(f"{task_id}: a forced change needs a granted state_override approval")
            req("state_override")
            need("state_override", _request_hint("state_override", task_id),
                 "the owner grants it with python3 tools/approve.py grant <ID> --by owner")
    else:
        hard.extend(pre)
    return finish()


def _check_gates(root, task: dict, task_id: str, policy_on: bool, pre: List[str],
                 warnings: List[str], req, need) -> None:
    gates = [gate for gate in task.get("gates") or []
             if isinstance(gate, str) and gate.strip()]
    passed = evidence.passing_gates(root, task_id)
    missing = [gate for gate in gates if gate not in passed]
    if not missing:
        return
    names = ", ".join(missing)
    if policy_on:
        pre.append(f"{task_id}: no passing gate record for {names}")
        req("gates")
        for gate in missing:
            need("gate", f"python3 tools/gate.py --task {task_id} --name {gate} -- <command>",
                 f"run gate {gate} and record a passing result")
    else:
        warnings.append(f"{task_id}: no passing gate record for {names} "
                        "(no policy.json: not enforced)")


# ---------------------------------------------------------------------------
# writing the board
# ---------------------------------------------------------------------------

def _write_board(root, board: dict) -> None:
    """Rewrite board.json atomically; the caller holds board.json.lock."""
    path = Path(root) / BOARD
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    tmp.write_text(json.dumps(board, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _next_command(task_id: str, status: str) -> Optional[str]:
    target = NEXT_STATUS.get(status)
    return _state_hint(task_id, target) if target else None


def set_status(root, task_id, new_status, *, actor: str = "lead", note=None,
               force: bool = False) -> dict:
    """Change one task status after its checkpoints passed, and record it.

    Raises :class:`TransitionBlocked` (with ``.errors`` and ``.actions``) when a
    checkpoint refuses. Returns the applied transition plus its side effects
    (``attempt``, ``max_attempts``, ``round``, ``next``) and warnings.
    """
    root = Path(root)
    if not isinstance(task_id, str) or not task_id.strip():
        raise PolierError("a state change needs a task id")
    task_id = task_id.strip()
    board_file = root / BOARD
    with FileLock(board_file.with_name(board_file.name + ".lock")):
        board = load_board(root)
        result = check_transition(root, board, task_id, new_status,
                                  actor=actor, note=note, force=force)
        if not result["ok"]:
            raise TransitionBlocked(result)
        entry = next((item for item in tasks_of(board) if item.get("id") == task_id), None)
        if entry is None:  # pragma: no cover - check_transition already refuses
            raise PolierError(f"task {task_id} is not on the board")
        previous = result["from"]
        policy, _warning = _policy(root)
        limits = policy_limits(policy)

        if new_status == "in_progress":
            start_attempt(root, task_id, actor)
        elif new_status == "done":
            finish_attempt(root, task_id, "pass", note)
        elif new_status == "rework":
            entry["round"] = _int(entry.get("round")) + 1
            finish_attempt(root, task_id, "fail", note)
        elif new_status == "blocked":
            finish_attempt(root, task_id, "cancelled", note)
        elif new_status == "failed":
            finish_attempt(root, task_id, "fail", note)

        state_event = {"from": previous, "to": new_status, "actor": actor}
        if _text(note):
            state_event["note"] = _text(note)
        append_event(root, task_id, "state", state_event)
        if new_status == "blocked":
            append_event(root, task_id, "escalate",
                         {"actor": actor, "note": note, "status": "blocked"})
        if force:
            append_event(root, task_id, "note", {
                "warning": f"forced transition {previous} → {new_status}",
                "overridden": list(result.get("forced") or []),
            })

        entry["status"] = new_status
        _write_board(root, board)
        attempts = attempt_count(root, task_id)
        return {
            "ok": True,
            "task": task_id,
            "from": previous,
            "to": new_status,
            "actor": actor,
            "note": note,
            "warnings": result["warnings"],
            "requires": result["requires"],
            "actions": result["actions"],
            "forced": result["forced"],
            "attempt": attempts,
            "attempts": attempts,
            "max_attempts": limits["max_attempts_per_task"],
            "round": _int(entry.get("round")),
            "state": run_state(root, task_id),
            "next": _next_command(task_id, new_status),
        }


def status_of(root, task_id) -> dict:
    """Board status against run record, gates, review, handoff and approvals."""
    root = Path(root)
    if not isinstance(task_id, str) or not task_id.strip():
        raise PolierError("status_of needs a task id")
    task_id = task_id.strip()
    board = load_board(root)
    task = next((item for item in tasks_of(board) if item.get("id") == task_id), None)
    if task is None:
        raise PolierError(f"task {task_id} is not on the board")
    policy, policy_warning = _policy(root)
    policy_on = policy_enabled(policy)
    limits = policy_limits(policy)
    record = load_run(root, task_id)
    gates = [gate for gate in task.get("gates") or [] if isinstance(gate, str)]
    passed = evidence.passing_gates(root, task_id)
    manifest = _dependency_manifest(policy, task)
    approved = [item for item in load_all(root)
                if item.get("status") == "granted"
                and (item.get("task") in (None, task_id))]
    out = {
        "task": task_id,
        "status": task.get("status"),
        "state": record["state"],
        "attempt": record["attempt"],
        "attempts": record["attempt"],
        "max_attempts": limits["max_attempts_per_task"],
        "round": _int(task.get("round")),
        "stage": task_stage_id(board, task),
        "gates": gates,
        "passed": sorted(passed),
        "missing_gates": [gate for gate in gates if gate not in passed],
        "review": {
            "file": f"reviews/{task_id}.md",
            "present": (root / REVIEW / f"{task_id}.md").is_file(),
            "verdict": _review_verdict(root, task_id),
        },
        "handoff": [line for line in task.get("handoff") or [] if isinstance(line, str)],
        "run_record": run_path(root, task_id).is_file(),
        "dependency_manifest": manifest,
        "new_dependency_granted": has_grant(root, "new_dependency", task_id),
        "approvals_pending": pending_approvals(root, task_id),
        "approvals_granted": approved,
        "events": len(record["events"]),
        "last_event": record["events"][-1] if record["events"] else None,
        "policy": policy_on,
        "updated": record["updated"],
    }
    if policy_warning:
        out["policy_warning"] = policy_warning
    return out
