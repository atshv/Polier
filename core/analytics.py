"""Analytics (2.2): the project's health from evidence, not from story points.

Every number is derived from the files Polier already writes: board statuses,
run events (attempts, state changes, gate results), evidence records, token
usage and sessions. There is no separate metrics store; the endpoint recomputes
the model from the project and the dashboard caches the snapshot.

Definitions used here:

- **throughput** — tasks whose state event says ``done`` per ISO week,
- **cycle time** — per stage, the time from the first work event
  (``claimed``/``in_progress``) to the ``done`` event of a task,
- **gate pass rate** — passing evidence records / all gate records,
- **rework rate** — tasks with a review round or a ``rework`` event / started tasks,
- **blocked age** — days since a task last moved to ``blocked``.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import dashboard as dashboard_mod
from . import evidence as evidence_mod
from . import runs as runs_mod
from . import worklog as worklog_mod

WEEKS = 12
STARTED = {"claimed", "in_progress", "verifying", "review", "rework", "done", "blocked", "failed"}


def _date(value: Any) -> Optional[dt.date]:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        return None


def _iso_week(day: dt.date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def _week_label(day: dt.date) -> str:
    return _iso_week(day)


def _week_start(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


def build(root, *, snapshot: Optional[dict] = None,
          worklog: Optional[dict] = None, today: Optional[dt.date] = None) -> Dict[str, Any]:
    root = Path(root).resolve()
    snapshot = snapshot if snapshot is not None else dashboard_mod.snapshot(root)
    worklog = worklog if worklog is not None else worklog_mod.project_worklog(root, snapshot["tasks"])
    today = today or dt.date.today()
    tasks = snapshot.get("tasks") or []
    task_by_id = {str(task.get("id")): task for task in tasks}
    records = evidence_mod.gate_records(root)

    # Run events: one pass over runs/.
    events_by_task: Dict[str, List[dict]] = {}
    for path in sorted((root / "runs").glob("*.json")):
        try:
            record = runs_mod.load_run(root, path.stem)
        except Exception:  # noqa: BLE001 - analytics must survive a broken run file
            continue
        events_by_task[path.stem] = [event for event in record.get("events") or []
                                     if isinstance(event, dict)]

    status_counts: Dict[str, int] = {}
    done = 0
    for task in tasks:
        status = str(task.get("status") or "?")
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "done":
            done += 1

    gate_results: Dict[str, int] = {}
    for record in records:
        result = str(record.get("result") or "?")
        gate_results[result] = gate_results.get(result, 0) + 1
    gate_total = sum(gate_results.values())
    gate_pass = gate_results.get("pass", 0)
    gate_pass_rate = round(gate_pass / gate_total, 3) if gate_total else None

    # Throughput: done events per ISO week (last WEEKS weeks, oldest first).
    week_done: Dict[str, int] = {}
    for task_id, events in events_by_task.items():
        for event in events:
            if event.get("kind") != "state":
                continue
            data = event.get("data") or {}
            if data.get("to") != "done":
                continue
            day = _date(event.get("at"))
            if day:
                week_done[_iso_week(day)] = week_done.get(_iso_week(day), 0) + 1
    throughput: List[dict] = []
    start_week = _week_start(today) - dt.timedelta(weeks=WEEKS - 1)
    for offset in range(WEEKS):
        week = _iso_week(start_week + dt.timedelta(weeks=offset))
        throughput.append({"week": week, "label": week, "done": week_done.get(week, 0)})

    # Cycle time per stage for done tasks.
    stage_seconds: Dict[str, List[float]] = {}
    for task_id, task in task_by_id.items():
        if task.get("status") != "done":
            continue
        stage = str(task.get("stage") or "(none)")
        first = None
        last = None
        for event in events_by_task.get(task_id, []):
            if event.get("kind") != "state":
                continue
            data = event.get("data") or {}
            moment = event.get("at")
            if data.get("to") in ("claimed", "in_progress") and first is None:
                first = moment
            if data.get("to") == "done":
                last = moment
        begin, end = _date(first), _date(last)
        if begin and end:
            stage_seconds.setdefault(stage, []).append(max(0.0, (end - begin).days))
    cycle_time = [
        {"stage": stage, "tasks": len(values),
         "avg_days": round(sum(values) / len(values), 2),
         "max_days": max(values)}
        for stage, values in sorted(stage_seconds.items())
    ]

    # Rework: tasks with a review round or a rework event.
    rework = 0
    for task in tasks:
        if int(task.get("round") or 0) > 0:
            rework += 1
            continue
        for event in events_by_task.get(str(task.get("id")), []):
            if event.get("kind") == "state" and (event.get("data") or {}).get("to") == "rework":
                rework += 1
                break
    started = len([task for task in tasks if int(task.get("attempt") or 0) > 0
                   or task.get("status") in STARTED])
    rework_rate = round(rework / started, 3) if started else 0.0

    # Blocked age: days since the latest move to blocked, for tasks blocked now.
    blocked_ages: List[float] = []
    for task in tasks:
        if task.get("status") != "blocked":
            continue
        latest = None
        for event in events_by_task.get(str(task.get("id")), []):
            if event.get("kind") == "state" and (event.get("data") or {}).get("to") == "blocked":
                day = _date(event.get("at"))
                if day and (latest is None or day > latest):
                    latest = day
        if latest:
            blocked_ages.append(max(0.0, (today - latest).days))

    sessions = worklog_mod.session_records(root)
    session_counts: Dict[str, int] = {}
    for session in sessions:
        status = str(session.get("status") or "?")
        session_counts[status] = session_counts.get(status, 0) + 1
    totals = worklog.get("totals") or {}

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "kpis": {
            "tasks_total": len(tasks),
            "tasks_done": done,
            "tasks_open": len(tasks) - done,
            "status_counts": status_counts,
            "completion": round(done / len(tasks), 3) if tasks else 0.0,
            "tokens_total": int(totals.get("tokens") or 0),
            "estimate_hours": totals.get("estimate_hours") or 0.0,
            "actual_hours": totals.get("actual_hours") or 0.0,
            "estimate_delta_hours": round(float(totals.get("actual_hours") or 0.0)
                                          - float(totals.get("estimate_hours") or 0.0), 2),
            "sessions_total": len(sessions),
            "session_counts": session_counts,
            "attempts_total": int(totals.get("attempts") or 0),
            "gate_total": gate_total,
            "gate_pass_rate": gate_pass_rate,
            "rework_tasks": rework,
            "rework_rate": rework_rate,
            "blocked_now": len(blocked_ages),
            "blocked_avg_days": round(sum(blocked_ages) / len(blocked_ages), 2) if blocked_ages else 0.0,
            "blocked_max_days": max(blocked_ages) if blocked_ages else 0.0,
        },
        "throughput": throughput,
        "throughput_total": sum(item["done"] for item in throughput),
        "cycle_time": cycle_time,
        "gate_results": [{"result": result, "count": count}
                         for result, count in sorted(gate_results.items())],
        "effort": {
            "totals": totals,
            "stages": worklog.get("stages") or [],
        },
        "sessions": {
            "counts": session_counts,
            "tokens": sum(int(session.get("tokens") or 0) for session in sessions),
            "total_seconds": round(sum(float(session.get("seconds") or 0.0) for session in sessions), 1),
        },
    }
