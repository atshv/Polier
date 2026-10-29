"""The dispatch plan: what the board says can run now, in parallel, and what cannot.

The board is the plan state; this module turns it into an execution plan without
writing anything (``tools/dispatch.py`` prints it, ``pl_next`` returns it as
JSON). Candidates are the ready tasks of ``core.board.ready_tasks``. A candidate
is left out of the waves when it is claimed by a live session (it is running
then), when it used its attempt limit (the plan names the escalation command) or
when its brief ``tasks/<ID>.md`` is missing.

Concurrency contract: candidates with the same non-empty ``parallel_group`` and
the same stage may share a wave only when their ``scope_write`` entries are
pairwise disjoint; a task without a group is a wave of its own. Groups are
packed in board order up to ``max_in_progress`` tasks per wave. An overlapping
scope is reported under ``conflicts``; only the first task stays in the wave
unless ``checks.disjoint_scopes`` is false, which keeps both in the wave and
turns the exclusion into a warning in the plan.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from . import approvals, runs
from .board import load_board, ready_tasks, stage_key, stage_report, task_stage_id, tasks_of
from .claims import live_claims
from .errors import PolierError
from .paths import inside, normalized
from .policy import (budget as policy_budget, checks as policy_checks, enabled as policy_enabled,
                     limits as policy_limits, load_policy)

# Board statuses of a task that is being worked on and therefore reported as
# running instead of being put into a wave.
RUNNING_STATUSES = ("claimed", "in_progress", "verifying", "review", "rework")


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _group(task: dict) -> Optional[str]:
    """The task's ``parallel_group`` when it is a non-empty string, else None."""
    group = _text(task.get("parallel_group"))
    return group or None


def _state_command(task_id: str, status: str) -> str:
    return f"python3 tools/state.py set {task_id} {status}"


def _brief_path(task_id: str) -> str:
    return f"tasks/{task_id}.md"


def _scope_entries(task: dict) -> List[str]:
    value = task.get("scope_write")
    return [entry for entry in value if isinstance(entry, str)] if isinstance(value, list) else []


def _overlap(a: dict, b: dict) -> List[str]:
    """The ``scope_write`` entries of both tasks that overlap, in board order."""
    paths: List[str] = []
    for left in _scope_entries(a):
        for right in _scope_entries(b):
            first, second = normalized(left), normalized(right)
            if not first or not second:
                continue
            if (inside(first, second) or inside(second, first)):
                for entry in (left, right):
                    if entry not in paths:
                        paths.append(entry)
    return paths


def _claim_summary(claim: dict) -> dict:
    """The claim fields a plan shows: who works on the task now."""
    return {"harness": claim.get("harness"), "session": claim.get("session")}


class _Plan:
    """One evalutation of the board; the public entry point is :func:`plan`."""

    def __init__(self, root: Path, board: dict, policy: dict, limit=None):
        self.root = root
        self.board = board
        self.policy = policy if isinstance(policy, dict) else {"enabled": False}
        self.policy_on = policy_enabled(self.policy)
        self.limits = policy_limits(self.policy)
        self.checks = policy_checks(self.policy)
        self.max_attempts = self.limits["max_attempts_per_task"]
        self.max_in_progress = self.limits["max_in_progress"]
        self.max_tokens = policy_budget(self.policy)["max_tokens_per_task"]
        per_wave = self.max_in_progress
        if isinstance(limit, int) and not isinstance(limit, bool) and limit > 0:
            per_wave = min(per_wave, limit)
        self.per_wave = max(per_wave, 1)

        self.tasks = tasks_of(board)
        self.by_id = {task.get("id"): task for task in self.tasks if isinstance(task.get("id"), str)}
        self.claims = {claim.get("task"): claim for claim in live_claims(root)
                       if isinstance(claim.get("task"), str)}
        self.readiness = self._readiness()

    # -- readiness ---------------------------------------------------------

    def _readiness(self) -> dict:
        """Per task id: "ready", "waits", "stage-waits", "stopped" or "not-pending"."""
        ready = {item["id"] for item in ready_tasks(self.board, self.root)}
        done = {task.get("id") for task in self.tasks if task.get("status") == "done"}
        reports = {entry["id"]: entry for entry in stage_report(self.board, self.root)}
        out: Dict[str, str] = {}
        for task in self.tasks:
            tid = task.get("id")
            if not isinstance(tid, str):
                continue
            if tid in ready:
                out[tid] = "ready"
                continue
            stage_id = task_stage_id(self.board, task)
            stage = reports.get(stage_id) if stage_id else None
            if stage is not None and stage.get("stopped"):
                out[tid] = "stopped"
            elif stage is not None and stage.get("incomplete_deps"):
                out[tid] = "stage-waits"
            else:
                deps = task.get("depends_on") if isinstance(task.get("depends_on"), list) else []
                if any(dep not in done for dep in deps if isinstance(dep, str)):
                    out[tid] = "waits"
                else:
                    out[tid] = "not-pending"
        return out

    # -- running -----------------------------------------------------------

    def _running(self) -> List[dict]:
        """Active tasks plus ready tasks a live session has already claimed."""
        out: List[dict] = []
        for task in self.tasks:
            tid = task.get("id")
            status = task.get("status")
            if not isinstance(tid, str):
                continue
            claimed_ready = (status == "pending" and tid in self.claims
                             and self.readiness.get(tid) == "ready")
            if status not in RUNNING_STATUSES and not claimed_ready:
                continue
            claim = self.claims.get(tid)
            out.append({
                "id": tid,
                "title": task.get("title"),
                "status": status,
                "attempt": runs.attempt_count(self.root, tid),
                "max_attempts": self.max_attempts,
                "tokens": runs.usage_total(self.root, tid),
                "max_tokens": self.max_tokens,
                "claim": _claim_summary(claim) if claim else None,
            })
        return out

    # -- blocked -----------------------------------------------------------

    def _blocked(self) -> List[dict]:
        """Pending tasks that cannot be dispatched, each with a next-step action."""
        out: List[dict] = []
        for task in self.tasks:
            tid = task.get("id")
            if not isinstance(tid, str) or task.get("status") != "pending":
                continue
            claim = self.claims.get(tid)
            state = self.readiness.get(tid, "not-pending")

            if state == "ready":
                used = runs.attempt_count(self.root, tid)
                if self.policy_on and used >= self.max_attempts:
                    out.append({
                        "id": tid,
                        "reason": f"attempts {used}/{self.max_attempts} used — escalate",
                        "action": _state_command(tid, "blocked")
                                  + f' --note "attempts {used}/{self.max_attempts} used; '
                                    f'what is needed"',
                    })
                elif self._over_budget(tid):
                    out.append({
                        "id": tid,
                        "reason": f"token budget used ({runs.usage_total(self.root, tid):,}"
                                  f"/{self.max_tokens:,}) — escalate",
                        "action": _state_command(tid, "blocked") + ' --note "token budget used"',
                    })
                elif not (self.root / _brief_path(tid)).is_file():
                    out.append({
                        "id": tid,
                        "reason": f"brief {_brief_path(tid)} is missing",
                        "action": f"write {_brief_path(tid)}",
                    })
                continue

            if claim is not None:
                harness = claim.get("harness") or "unknown harness"
                out.append({
                    "id": tid,
                    "reason": f"claimed by another session ({harness})",
                    "action": "python3 tools/claim.py list",
                })
            elif state == "stopped":
                out.append({
                    "id": tid,
                    "reason": "stage stopped by the owner",
                    "action": f"python3 tools/state.py show {tid} --json",
                })
            elif state == "stage-waits":
                stage_id = task_stage_id(self.board, task) or "?"
                report = {entry["id"]: entry for entry in stage_report(self.board, self.root)}
                waiting = ", ".join(report.get(stage_id, {}).get("incomplete_deps") or [])
                out.append({
                    "id": tid,
                    "reason": f"stage waits for {waiting}",
                    "action": "python3 tools/dispatch.py --json",
                })
            elif state == "waits":
                done = {entry.get("id") for entry in self.tasks if entry.get("status") == "done"}
                deps = [dep for dep in task.get("depends_on") or []
                        if isinstance(dep, str) and dep not in done]
                waiting = ", ".join(deps) or "its dependencies"
                action = (f"python3 tools/state.py show {deps[0]} --json"
                          if deps else "python3 tools/dispatch.py --json")
                out.append({
                    "id": tid,
                    "reason": f"waits for {waiting}",
                    "action": action,
                })
        return out

    # -- waves -------------------------------------------------------------

    def _wave_entry(self, task: dict) -> dict:
        return {
            "id": task.get("id"),
            "title": task.get("title"),
            "brief": _brief_path(task.get("id")),
            "parallel_group": _group(task),
        }

    def _waves(self) -> tuple:
        """(waves, conflicts) for the ready, unclaimed candidates in board order."""
        specs: List[tuple] = []
        members: Dict[tuple, List[dict]] = {}
        displaced = {
            task.get("id") for task in self.tasks
            if isinstance(task.get("id"), str) and self.readiness.get(task.get("id")) == "ready"
            and (task.get("id") in self.claims
                 or (self.policy_on
                     and runs.attempt_count(self.root, task.get("id")) >= self.max_attempts)
                 or self._over_budget(task.get("id"))
                 or not (self.root / _brief_path(task.get("id"))).is_file())
        }
        for task in self.tasks:
            tid = task.get("id")
            if not isinstance(tid, str) or tid not in self.by_id or tid in displaced:
                continue
            if self.readiness.get(tid) != "ready":
                continue
            group = _group(task)
            if group is None:
                specs.append(("one", task))
                continue
            key = (stage_key(task.get("stage")), group)
            if key not in members:
                members[key] = []
                specs.append(("group", key))
            members[key].append(task)

        waves: List[List[dict]] = []
        conflicts: List[dict] = []
        for kind, value in specs:
            if kind == "one":
                waves.append([self._wave_entry(value)])
                continue
            group_members = members[value]
            for start in range(0, len(group_members), self.per_wave):
                chunk = group_members[start:start + self.per_wave]
                kept: List[dict] = []
                for task in chunk:
                    overlapping = [(other, _overlap(other, task)) for other in kept]
                    overlapping = [(other, paths) for other, paths in overlapping if paths]
                    if not overlapping:
                        kept.append(task)
                        continue
                    for other, paths in overlapping:
                        conflicts.append({"a": other.get("id"), "b": task.get("id"),
                                          "paths": paths})
                    if self.checks.get("disjoint_scopes", True) is False:
                        kept.append(task)
                if kept:
                    waves.append([self._wave_entry(task) for task in kept])
        return waves, conflicts

    def _over_budget(self, tid) -> bool:
        return bool(self.max_tokens) and runs.usage_total(self.root, tid) >= self.max_tokens

    def result(self) -> dict:
        waves, conflicts = self._waves()
        return {
            "project": self.board.get("project"),
            "profile": self.board.get("profile"),
            "limits": {"max_attempts_per_task": self.max_attempts,
                       "max_in_progress": self.max_in_progress},
            "running": self._running(),
            "waves": waves,
            "blocked": self._blocked(),
            "conflicts": conflicts,
            "approvals_pending": [{"id": record.get("id"), "action": record.get("action"),
                                   "task": record.get("task")}
                                  for record in approvals.pending(self.root)],
            "next": [entry["id"] for entry in waves[0]] if waves else [],
        }


def plan(root, board=None, policy=None, limit=None) -> dict:
    """The dispatch plan of ``root`` as a dict; nothing is written.

    ``board`` and ``policy`` may be passed in (``tools/check.py`` has them
    already); by default both are loaded from ``root``. A project without
    ``policy.json`` keeps the 1.0 behaviour: the attempt limit is not enforced
    (the plan lists no attempt-exhausted block) and the defaults only inform the
    wave size. ``limit`` caps the tasks per wave on top of ``max_in_progress``.
    """
    root = Path(root)
    if board is None:
        board = load_board(root, strict=False)
        if board is None:
            raise PolierError(f"board.json not found in {root}")
    if policy is None:
        try:
            policy = load_policy(root)
        except PolierError:
            policy = {"enabled": False}
    if not isinstance(board, dict):
        raise PolierError("board.json has no task list")
    return _Plan(root, board, policy, limit=limit).result()
