"""Cycles (2.2): the stages as time-boxed execution units, with real evidence.

A "cycle" in Polier is a stage: it has a goal, exit criteria, exit gates and an
owner decision, and it completes when its tasks are done — not when a calendar
date passes. This module turns the existing stage report, run records, evidence
and worklog into one model the dashboard can render: progress, gate coverage,
effort, owner decision and a burndown built from the run events.

Nothing is stored or computed by dates that are not already in the project; the
burndown uses the timestamps of ``state`` events in ``runs/``.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import dashboard as dashboard_mod
from . import runs as runs_mod
from . import worklog as worklog_mod

BURNDOWN_DAYS = 42


def _date(value: Any) -> Optional[dt.date]:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        return None


def _done_dates(root: Path, task_ids: List[str]) -> Dict[str, dt.date]:
    dates: Dict[str, dt.date] = {}
    for task_id in task_ids:
        try:
            record = runs_mod.load_run(root, task_id)
        except Exception:  # noqa: BLE001 - a broken run file must not break the view
            continue
        for event in record.get("events") or []:
            if not isinstance(event, dict) or event.get("kind") != "state":
                continue
            data = event.get("data") or {}
            if data.get("to") != "done":
                continue
            moment = _date(event.get("at"))
            if moment:
                dates[task_id] = moment
    return dates


def _burndown(total: int, done: Dict[str, dt.date], today: dt.date) -> List[dict]:
    if not done:
        return [{"date": today.isoformat(), "remaining": total, "done": 0}]
    first = min(done.values())
    start = max(first, today - dt.timedelta(days=BURNDOWN_DAYS))
    series: List[dict] = []
    current = start
    while current <= today:
        finished = len([done_date for done_date in done.values() if done_date <= current])
        series.append({"date": current.isoformat(), "remaining": max(0, total - finished),
                       "done": finished})
        current += dt.timedelta(days=1)
    return series


def build(root, *, snapshot: Optional[dict] = None,
          worklog: Optional[dict] = None, today: Optional[dt.date] = None) -> Dict[str, Any]:
    root = Path(root).resolve()
    snapshot = snapshot if snapshot is not None else dashboard_mod.snapshot(root)
    worklog = worklog if worklog is not None else worklog_mod.project_worklog(root, snapshot["tasks"])
    worklog_rows = {row["id"]: row for row in worklog.get("tasks") or []}
    today = today or dt.date.today()
    board_stage = (snapshot.get("project") or {}).get("stage")
    stages = snapshot.get("stages") or []
    tasks = {str(task.get("id")): task for task in snapshot.get("tasks") or []}
    cycles: List[Dict[str, Any]] = []
    for index, stage in enumerate(stages):
        stage_id = str(stage.get("id"))
        stage_tasks = [tasks[task_id] for task_id in stage.get("tasks") or [] if task_id in tasks]
        task_ids = [str(task.get("id")) for task in stage_tasks]
        counts: Dict[str, int] = {}
        for task in stage_tasks:
            status = str(task.get("status") or "?")
            counts[status] = counts.get(status, 0) + 1
        total = len(stage_tasks)
        done = counts.get("done", 0)
        done_dates = _done_dates(root, task_ids)
        rows = [worklog_rows.get(task_id) for task_id in task_ids]
        rows = [row for row in rows if row]
        exit_gates = [gate for gate in stage.get("exit_gates") or [] if isinstance(gate, str)]
        missing = [gate for gate in stage.get("missing_gates") or [] if isinstance(gate, str)]
        complete = bool(stage.get("complete"))
        if complete:
            status = "completed"
        elif isinstance(board_stage, int) and board_stage == index + 1:
            status = "active"
        else:
            first_open = next(((position, entry) for position, entry in enumerate(stages)
                               if not entry.get("complete")), None)
            status = "active" if first_open and first_open[0] == index else "upcoming"
        cycles.append({
            "id": stage_id,
            "title": stage.get("title") or stage_id,
            "index": stage.get("index") or index + 1,
            "goal": stage.get("goal"),
            "status": status,
            "complete": complete,
            "owner_decision": stage.get("owner_decision"),
            "stopped": bool(stage.get("stopped")),
            "depends_on": stage.get("depends_on") or [],
            "exit_criteria": stage.get("exit_criteria") or [],
            "exit_gates": [{"name": gate, "passed": gate not in missing} for gate in exit_gates],
            "exit_gates_passed": len([gate for gate in exit_gates if gate not in missing]),
            "exit_gates_total": len(exit_gates),
            "counts": counts,
            "total": total,
            "done": done,
            "progress": round(done / total, 3) if total else 0.0,
            "tasks": [{"id": task.get("id"), "title": task.get("title"),
                       "status": task.get("status"), "owner": task.get("owner")}
                      for task in stage_tasks],
            "tasks_open": [str(task_id) for task_id in stage.get("tasks_open") or []],
            "tokens": sum(int(row.get("tokens") or 0) for row in rows),
            "estimate_hours": round(sum(float(row.get("estimate_hours") or 0.0) for row in rows), 1),
            "actual_hours": round(sum(float(row.get("actual_hours") or 0.0) for row in rows), 1),
            "sessions": sum(int(row.get("sessions") or 0) for row in rows),
            "burndown": _burndown(total, done_dates, today),
        })
    active = next((cycle for cycle in cycles if cycle["status"] == "active"), None)
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "active": active["id"] if active else None,
        "cycles": cycles,
        "totals": {
            "cycles": len(cycles),
            "completed": len([cycle for cycle in cycles if cycle["status"] == "completed"]),
            "tasks": sum(cycle["total"] for cycle in cycles),
            "done": sum(cycle["done"] for cycle in cycles),
            "tokens": sum(cycle["tokens"] for cycle in cycles),
            "estimate_hours": round(sum(cycle["estimate_hours"] for cycle in cycles), 1),
            "actual_hours": round(sum(cycle["actual_hours"] for cycle in cycles), 1),
        },
    }
