"""Your Work and Inbox (2.1): the owner's queue, derived, with a small read state.

Nothing here is stored as project state: the items come from the board, the run
records, the approvals, the evidence and the sessions. Only "read/unread" is a
local preference and lives in
``<git-common-dir>/polier/dashboard/inbox.json``.

The identity is the project's ``dashboard.json`` → ``defaults.me`` (a handle such
as ``owner`` or ``lead``); tasks with that ``owner`` are "mine", everything else
is the shared queue.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import approvals as approvals_mod
from . import dashboard as dashboard_mod
from . import evidence as evidence_mod
from . import runtime as runtime_mod
from . import settings as settings_mod
from . import worklog as worklog_mod

READ_FILE = "inbox.json"
SCHEMA = 1
SEVERITY = {"high": 0, "medium": 1, "low": 2, "info": 3}
BAD_GATE_RESULTS = frozenset({"fail", "infra", "busy", "timeout"})
MAX_READ = 500


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def identity(root, settings: Optional[dict] = None) -> Dict[str, Any]:
    settings = settings if settings is not None else settings_mod.load(root)
    return {"me": settings_mod.me(settings), "project": _text(
        (board_project(root) or ""))}


def board_project(root) -> Optional[str]:
    try:
        board = json.loads((Path(root) / "board.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return board.get("project") if isinstance(board, dict) else None


# -- read state -------------------------------------------------------------

def _read_path(root: Path) -> Path:
    return runtime_mod.runtime_dir(root) / READ_FILE


def read_state(root) -> Dict[str, Any]:
    state = runtime_mod.read_json(_read_path(Path(root)))
    read = state.get("read")
    return {"version": SCHEMA, "read": read if isinstance(read, dict) else {},
            "updated": state.get("updated")}


def mark_read(root, ids: Optional[List[str]] = None, *, read: bool = True,
              all_items: bool = False, reset: bool = False) -> Dict[str, Any]:
    """Mark item ids read/unread. ``all_items`` marks the current inbox read;
    ``reset`` clears the read map (everything becomes unread again)."""
    root = Path(root).resolve()
    state = read_state(root)
    mapping = dict(state.get("read") or {})
    if reset:
        mapping = {}
    else:
        targets = list(ids or [])
        if all_items:
            targets.extend(item["id"] for item in inbox(root)
                           if isinstance(item.get("id"), str))
        for item_id in targets:
            if not isinstance(item_id, str) or not item_id.strip():
                continue
            if read:
                mapping[item_id] = _now()
            else:
                mapping.pop(item_id, None)
    if len(mapping) > MAX_READ:
        keep = sorted(mapping.items(), key=lambda pair: str(pair[1]))[-MAX_READ:]
        mapping = dict(keep)
    value = {"version": SCHEMA, "read": mapping, "updated": _now()}
    runtime_mod.write_json(_read_path(root), value)
    return value


# -- derived views ----------------------------------------------------------

def _sessions(root) -> List[Dict[str, Any]]:
    return worklog_mod.session_records(root)


def your_work(root, snapshot: Optional[dict] = None,
              settings: Optional[dict] = None) -> Dict[str, Any]:
    """The personal cockpit: my tasks, reviews, approvals, claims, sessions."""
    root = Path(root).resolve()
    settings = settings if settings is not None else settings_mod.load(root)
    me = settings_mod.me(settings)
    snapshot = snapshot if snapshot is not None else dashboard_mod.snapshot(root)
    tasks = snapshot.get("tasks") or []
    mine = [task for task in tasks if _text(task.get("owner")) == me]
    claimed = [task for task in tasks if task.get("claim")]
    reviews = [task for task in tasks if task.get("status") in ("review", "verifying")]
    blocked = [task for task in tasks if task.get("blocked_reason") or task.get("status") == "blocked"]
    budget = [task for task in tasks if (task.get("budget") or {}).get("over")
              or (task.get("budget") or {}).get("warn")]
    ready = [task for task in tasks if task.get("ready") and task.get("wave") == 0]
    sessions = _sessions(root)
    running = [session for session in sessions if session.get("status") in ("starting", "running")]
    pending_approvals = [record for record in approvals_mod.load_all(root)
                         if record.get("status") == "pending"]
    workload: Dict[str, int] = {}
    for task in mine:
        status = _text(task.get("status")) or "?"
        workload[status] = workload.get(status, 0) + 1
    return {
        "me": me,
        "project": _text((snapshot.get("project") or {}).get("name")),
        "generated_at": _now(),
        "counts": {
            "mine": len(mine),
            "claimed": len(claimed),
            "reviews": len(reviews),
            "approvals": len(pending_approvals),
            "blocked": len(blocked),
            "budget": len(budget),
            "ready": len(ready),
            "sessions_running": len(running),
        },
        "workload": workload,
        "mine": [{"id": task.get("id"), "title": task.get("title"), "status": task.get("status"),
                  "stage": task.get("stage"), "tokens": task.get("tokens"),
                  "gates_missing": task.get("gates_missing")} for task in mine],
        "reviews": [{"id": task.get("id"), "title": task.get("title"), "status": task.get("status"),
                     "owner": task.get("owner"), "review": task.get("review")} for task in reviews],
        "approvals": pending_approvals,
        "claimed": [{"id": task.get("id"), "title": task.get("title"),
                     "claim": task.get("claim")} for task in claimed],
        "blocked": [{"id": task.get("id"), "title": task.get("title"),
                     "reason": task.get("blocked_reason")} for task in blocked],
        "budget": [{"id": task.get("id"), "title": task.get("title"),
                    "budget": task.get("budget")} for task in budget],
        "ready": [{"id": task.get("id"), "title": task.get("title")} for task in ready],
        "sessions": [{"id": session.get("id"), "task": session.get("task"),
                      "role": session.get("role"), "status": session.get("status"),
                      "started": session.get("started"), "tokens": session.get("tokens")}
                     for session in sessions[:20]],
    }


def _gate_failures(root: Path) -> List[Dict[str, Any]]:
    latest: Dict[tuple, dict] = {}
    for record in evidence_mod.gate_records(root):
        task_id, gate = record.get("task"), record.get("gate")
        if not isinstance(task_id, str) or not isinstance(gate, str):
            continue
        key = (task_id, gate)
        previous = latest.get(key)
        if previous is None or str(record.get("started") or "") > str(previous.get("started") or ""):
            latest[key] = record
    failures = []
    for (task_id, gate), record in latest.items():
        if record.get("result") in BAD_GATE_RESULTS or record.get("exit_code") not in (0, None):
            failures.append({
                "task": task_id,
                "gate": gate,
                "result": record.get("result"),
                "at": record.get("finished") or record.get("started"),
                "record": record.get("log"),
            })
    return failures


def inbox(root, snapshot: Optional[dict] = None, settings: Optional[dict] = None,
          limit: int = 100) -> List[Dict[str, Any]]:
    """Actionable items, newest first inside each severity, with read state."""
    root = Path(root).resolve()
    settings = settings if settings is not None else settings_mod.load(root)
    snapshot = snapshot if snapshot is not None else dashboard_mod.snapshot(root)
    read = read_state(root).get("read") or {}
    tasks = {str(task.get("id")): task for task in snapshot.get("tasks") or []}
    items: List[Dict[str, Any]] = []

    def add(item_id: str, kind: str, severity: str, title: str, *, at=None,
            task=None, summary=None, action=None) -> None:
        items.append({
            "id": item_id, "kind": kind, "severity": severity, "title": title,
            "at": at, "task": task, "summary": summary, "action": action,
            "read": item_id in read,
        })

    for record in approvals_mod.load_all(root):
        if record.get("status") != "pending":
            continue
        approval_id = str(record.get("id"))
        add(f"approval:{approval_id}", "approval", "high",
            f"{approval_id}: {record.get('action')} approval needed",
            at=record.get("requested_at"), task=record.get("task"),
            summary=record.get("note"), action="Open approvals")
    for failure in _gate_failures(root):
        task = tasks.get(failure["task"]) or {}
        if task.get("status") == "done":
            continue
        record = str(failure.get("record") or failure.get("at"))
        add(f"gate:{failure['task']}:{failure['gate']}:{record}", "gate_failed", "high",
            f"Gate {failure['gate']} failed on {failure['task']}",
            at=failure.get("at"), task=failure["task"],
            summary=failure.get("result"), action="Open task")
    for task in snapshot.get("tasks") or []:
        task_id = str(task.get("id"))
        if task.get("blocked_reason") or task.get("status") == "blocked":
            add(f"blocked:{task_id}", "blocked", "medium",
                f"{task_id} is blocked", at=(task.get("run") or {}).get("updated"),
                task=task_id, summary=task.get("blocked_reason") or "blocked by the plan",
                action="Open task")
        budget = task.get("budget") or {}
        if budget.get("over"):
            add(f"budget:{task_id}", "budget", "high", f"{task_id} is over its token budget",
                at=(task.get("run") or {}).get("updated"), task=task_id,
                summary=f"{budget.get('used')} used", action="Open task")
        elif budget.get("warn"):
            add(f"budget:{task_id}", "budget", "medium", f"{task_id} is close to its token budget",
                at=(task.get("run") or {}).get("updated"), task=task_id,
                summary=f"{budget.get('used')} used", action="Open task")
        if task.get("status") in ("review", "verifying"):
            review = task.get("review") or {}
            if not review.get("present") or not review.get("verdict"):
                add(f"review:{task_id}", "review", "medium", f"{task_id} waits for a review",
                    at=(task.get("run") or {}).get("updated"), task=task_id,
                    summary=task.get("title"), action="Open task")
        if task.get("ready") and task.get("wave") == 0 and task.get("status") == "pending":
            add(f"ready:{task_id}", "ready", "info", f"{task_id} is ready to start",
                at=(task.get("run") or {}).get("updated"), task=task_id,
                summary=task.get("title"), action="Open task")
    for session in _sessions(root)[:20]:
        if session.get("status") not in ("failed", "stopped"):
            continue
        add(f"session:{session.get('id')}", "session", "medium" if session.get("status") == "failed" else "low",
            f"Session {session.get('id')} {session.get('status')}",
            at=session.get("ended"), task=session.get("task"),
            summary=f"{session.get('role')} · {session.get('tokens')} tokens", action="Open sessions")
    items.sort(key=lambda item: (SEVERITY.get(str(item.get("severity")), 9),
                                 str(item.get("at") or "")))
    return items[: max(1, int(limit))]


def inbox_summary(root, snapshot: Optional[dict] = None,
                  settings: Optional[dict] = None) -> Dict[str, Any]:
    items = inbox(root, snapshot=snapshot, settings=settings, limit=200)
    unread = [item for item in items if not item.get("read")]
    return {
        "items": items,
        "counts": {
            "total": len(items),
            "unread": len(unread),
            "high": len([item for item in unread if item.get("severity") == "high"]),
        },
    }
