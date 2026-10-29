"""Worklog (2.1): actual effort derived from run records, gate records and sessions.

Nothing here asks a human to stop a clock. The evidence Polier already writes is
the timesheet:

- ``runs/<ID>.json``: attempts (start/end/result), gate events, usage per session,
- ``reviews/evidence/*.json``: gate records with start/finish and duration,
- ``<git-common-dir>/polier/dashboard/sessions/*/meta.json``: headless sessions
  with role, start/end, tokens and status.

The task's optional ``estimate_hours`` (board schema 1.1) is compared with the
actual time. ``actual_hours`` prefers session time when sessions exist (the
agent ran) and falls back to the attempt window, never summing both — the
attempt contains the session.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import evidence as evidence_mod
from . import runs as runs_mod
from . import runtime as runtime_mod


def _parse(value: Any) -> Optional[dt.datetime]:
    if not isinstance(value, str) or not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def _seconds(started: Any, ended: Any) -> float:
    begin, end = _parse(started), _parse(ended)
    if begin is None or end is None:
        return 0.0
    return max(0.0, (end - begin).total_seconds())


def _round(value: float) -> float:
    return round(float(value), 2)


def session_records(root) -> List[Dict[str, Any]]:
    """Headless sessions of this project from the dashboard runtime folder."""
    folder = runtime_mod.runtime_dir(root) / "sessions"
    if not folder.is_dir():
        return []
    records: List[Dict[str, Any]] = []
    for path in sorted(folder.glob("*/meta.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(value, dict):
            continue
        value.setdefault("id", path.parent.name)
        value["seconds"] = _seconds(value.get("started"), value.get("ended"))
        records.append(value)
    records.sort(key=lambda item: str(item.get("started") or ""), reverse=True)
    return records


def task_worklog(root, task_id: str, *, task: Optional[dict] = None) -> Dict[str, Any]:
    """The worklog of one task, ready for the drawer."""
    root = Path(root).resolve()
    run = runs_mod.load_run(root, task_id)
    attempts: List[Dict[str, Any]] = []
    attempt_seconds = 0.0
    for entry in run.get("attempts") or []:
        if not isinstance(entry, dict):
            continue
        seconds = _seconds(entry.get("started"), entry.get("ended"))
        attempt_seconds += seconds
        attempts.append({
            "n": entry.get("n"),
            "started": entry.get("started"),
            "ended": entry.get("ended"),
            "result": entry.get("result"),
            "note": entry.get("note"),
            "seconds": _round(seconds),
        })
    usage = []
    tokens = 0
    for session, entry in (run.get("usage") or {}).items():
        if not isinstance(entry, dict):
            continue
        amount = entry.get("tokens")
        amount = int(amount) if isinstance(amount, (int, float)) else 0
        tokens += amount
        usage.append({"session": str(session), "tokens": amount,
                      "source": entry.get("source"), "updated": entry.get("updated")})
    usage.sort(key=lambda item: str(item.get("updated") or ""), reverse=True)

    sessions = [record for record in session_records(root) if record.get("task") == task_id]
    session_seconds = sum(float(record.get("seconds") or 0.0) for record in sessions)

    gates: List[Dict[str, Any]] = []
    gate_seconds = 0.0
    for record in evidence_mod.gate_records(root, task_id):
        seconds = _seconds(record.get("started"), record.get("finished"))
        gate_seconds += seconds
        gates.append({
            "gate": record.get("gate"), "result": record.get("result"),
            "exit_code": record.get("exit_code"), "started": record.get("started"),
            "finished": record.get("finished"), "seconds": _round(seconds),
            "record": record.get("log"), "command": record.get("command"),
        })
    gates.sort(key=lambda item: str(item.get("started") or ""), reverse=True)

    estimate = None
    if isinstance(task, dict):
        value = task.get("estimate_hours")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            estimate = float(value)
    actual_seconds = session_seconds if sessions else attempt_seconds
    actual_hours = _round(actual_seconds / 3600.0)
    delta = _round(actual_hours - estimate) if estimate is not None else None
    return {
        "task": task_id,
        "attempts": attempts,
        "sessions": [{
            "id": record.get("id"), "role": record.get("role"),
            "status": record.get("status"), "provider": record.get("provider"),
            "started": record.get("started"), "ended": record.get("ended"),
            "seconds": _round(float(record.get("seconds") or 0.0)),
            "tokens": int(record.get("tokens") or 0),
        } for record in sessions],
        "usage": usage,
        "gates": gates,
        "totals": {
            "attempts": len(attempts),
            "sessions": len(sessions),
            "gates": len(gates),
            "attempt_seconds": _round(attempt_seconds),
            "session_seconds": _round(session_seconds),
            "gate_seconds": _round(gate_seconds),
            "tokens": tokens,
        },
        "estimate_hours": estimate,
        "actual_hours": actual_hours,
        "delta_hours": delta,
    }


def project_worklog(root, tasks: List[dict]) -> Dict[str, Any]:
    """Per-task effort plus totals and stage sums, with one evidence scan."""
    root = Path(root).resolve()
    sessions_by_task: Dict[str, List[dict]] = {}
    for record in session_records(root):
        task_id = record.get("task")
        if isinstance(task_id, str):
            sessions_by_task.setdefault(task_id, []).append(record)
    records_by_task: Dict[str, List[dict]] = {}
    for record in evidence_mod.gate_records(root):
        task_id = record.get("task")
        if isinstance(task_id, str):
            records_by_task.setdefault(task_id, []).append(record)

    rows: List[Dict[str, Any]] = []
    stage_totals: Dict[str, Dict[str, float]] = {}
    total_tokens = total_estimate = total_actual = 0.0
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id") or "")
        if not task_id:
            continue
        run = runs_mod.load_run(root, task_id)
        attempt_seconds = 0.0
        for entry in run.get("attempts") or []:
            if isinstance(entry, dict):
                attempt_seconds += _seconds(entry.get("started"), entry.get("ended"))
        tokens = sum(int(entry.get("tokens") or 0) for entry in (run.get("usage") or {}).values()
                     if isinstance(entry, dict) and isinstance(entry.get("tokens"), (int, float)))
        sessions = sessions_by_task.get(task_id, [])
        session_seconds = sum(float(record.get("seconds") or 0.0) for record in sessions)
        gate_seconds = sum(_seconds(record.get("started"), record.get("finished"))
                           for record in records_by_task.get(task_id, []))
        actual_seconds = session_seconds if sessions else attempt_seconds
        actual_hours = _round(actual_seconds / 3600.0)
        estimate = task.get("estimate_hours")
        estimate = float(estimate) if isinstance(estimate, (int, float)) and not isinstance(estimate, bool) else None
        stage = str(task.get("stage") or "")
        row = {
            "id": task_id,
            "title": task.get("title"),
            "status": task.get("status"),
            "stage": stage,
            "owner": task.get("owner"),
            "labels": task.get("labels") or [],
            "estimate_hours": estimate,
            "actual_hours": actual_hours,
            "delta_hours": _round(actual_hours - estimate) if estimate is not None else None,
            "tokens": tokens,
            "attempts": len(run.get("attempts") or []),
            "sessions": len(sessions),
            "attempt_seconds": _round(attempt_seconds),
            "session_seconds": _round(session_seconds),
            "gate_seconds": _round(gate_seconds),
        }
        rows.append(row)
        bucket = stage_totals.setdefault(stage or "(none)", {
            "tasks": 0, "estimate_hours": 0.0, "actual_hours": 0.0, "tokens": 0, "sessions": 0,
        })
        bucket["tasks"] += 1
        bucket["actual_hours"] = _round(bucket["actual_hours"] + actual_hours)
        bucket["tokens"] += tokens
        bucket["sessions"] += len(sessions)
        if estimate is not None:
            bucket["estimate_hours"] = _round(bucket["estimate_hours"] + estimate)
        total_actual += actual_hours
        total_tokens += tokens
        if estimate is not None:
            total_estimate += estimate
    rows.sort(key=lambda row: str(row.get("id") or ""))
    return {
        "tasks": rows,
        "stages": [{"stage": stage, **values} for stage, values in sorted(stage_totals.items())],
        "totals": {
            "tasks": len(rows),
            "estimate_hours": _round(total_estimate),
            "actual_hours": _round(total_actual),
            "tokens": int(total_tokens),
            "sessions": sum(row["sessions"] for row in rows),
            "attempts": sum(row["attempts"] for row in rows),
        },
    }
