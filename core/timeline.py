"""Timeline (2.2): the plan on a time axis, without a calendar server.

The schedule is derived, not stored: tasks start after their dependencies, take
as long as their estimate (``estimate_hours``, else ``complexity × 2 h``) allows
at ``defaults.hours_per_day`` (dashboard.json, default 4), and run inside their
stage lane. Optional planning dates (board schema 1.2, ``planned_start`` and
``target``) override the auto-schedule for one task. Completed tasks are placed
where their run record says they finished, so the left side of the timeline
shows what already happened.

The result is a render-ready model: lanes (stages), tasks with start/end dates,
day/week axes, a critical path and the totals. No dates are written to the
board by rendering.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import board as board_mod
from . import runs as runs_mod
from . import settings as settings_mod
from .errors import PolierError

MAX_DAYS = 240
DEFAULT_HOURS_PER_DAY = 4.0
DEFAULT_TASK_HOURS = 2.0


def _date(value: Any) -> Optional[dt.date]:
    if not isinstance(value, str):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def _iso(value: Optional[dt.date]) -> Optional[str]:
    return value.isoformat() if value else None


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _task_hours(task: dict) -> float:
    estimate = _number(task.get("estimate_hours"))
    if estimate is not None:
        return max(0.5, estimate)
    complexity = _number(task.get("complexity"))
    if complexity is not None:
        return max(1.0, complexity * DEFAULT_TASK_HOURS)
    return DEFAULT_TASK_HOURS


def _duration(hours: float, hours_per_day: float) -> int:
    return max(1, int(math.ceil(hours / max(0.5, hours_per_day))))


def _done_dates(root: Path, task_ids: List[str]) -> Dict[str, dt.date]:
    dates: Dict[str, dt.date] = {}
    for task_id in task_ids:
        try:
            record = runs_mod.load_run(root, task_id)
        except Exception:  # noqa: BLE001 - a timeline must render with broken run records
            continue
        for event in record.get("events") or []:
            if not isinstance(event, dict) or event.get("kind") != "state":
                continue
            data = event.get("data") or {}
            if data.get("to") != "done":
                continue
            moment = event.get("at")
            if isinstance(moment, str) and len(moment) >= 10:
                try:
                    dates[task_id] = dt.date.fromisoformat(moment[:10])
                except ValueError:
                    pass
    return dates


def _stage_order(board: dict) -> List[dict]:
    stages = [stage for stage in board.get("stages") or [] if isinstance(stage, dict)]
    if stages:
        return stages
    return [{"id": "", "title": "All tasks"}]


def _lane_of(task: dict, stages: List[dict]) -> Optional[str]:
    """The stage lane of a task, or None when it does not fit a declared stage."""
    if not stages:
        return ""
    stage = task.get("stage")
    if isinstance(stage, str) and any(str(entry.get("id")) == stage for entry in stages):
        return stage
    if isinstance(stage, int):
        index = stage - 1
        if 0 <= index < len(stages):
            return str(stages[index].get("id") or "")
    return None


def _topological(tasks: List[dict]) -> List[dict]:
    by_id = {str(task.get("id")): task for task in tasks if isinstance(task, dict)}
    order: List[dict] = []
    visiting: set = set()
    done: set = set()

    def visit(task: dict) -> None:
        task_id = str(task.get("id"))
        if task_id in done:
            return
        if task_id in visiting:  # a cycle: keep board order, do not loop
            return
        visiting.add(task_id)
        for dependency in task.get("depends_on") or []:
            if isinstance(dependency, str) and dependency in by_id:
                visit(by_id[dependency])
        visiting.discard(task_id)
        done.add(task_id)
        order.append(task)

    for task in tasks:
        if isinstance(task, dict):
            visit(task)
    return order


def build(root, *, board: Optional[dict] = None, settings: Optional[dict] = None,
          today: Optional[dt.date] = None) -> Dict[str, Any]:
    """The timeline model for the dashboard, MCP and tests."""
    root = Path(root).resolve()
    board = board if board is not None else board_mod.load_board(root)
    if board is None:
        raise PolierError("no board.json; plan the project first")
    settings = settings if settings is not None else settings_mod.load(root)
    hours_per_day = settings_mod.hours_per_day(settings)
    today = today or dt.date.today()
    stages = _stage_order(board)
    stage_index = {str(stage.get("id") or ""): index for index, stage in enumerate(stages)}
    tasks = [task for task in board.get("tasks") or [] if isinstance(task, dict)]
    by_id = {str(task.get("id")): task for task in tasks}
    done_dates = _done_dates(root, list(by_id))

    # Stage windows: sequential in board order, honouring explicit stage dependencies.
    stage_start: Dict[str, dt.date] = {}
    stage_end: Dict[str, dt.date] = {}
    cursor = today
    for stage in stages:
        stage_id = str(stage.get("id") or "")
        start = cursor
        for dependency in stage.get("depends_on") or []:
            if isinstance(dependency, str) and dependency in stage_end:
                start = max(start, stage_end[dependency] + dt.timedelta(days=1))
        stage_start[stage_id] = start
        stage_end[stage_id] = start
        cursor = start + dt.timedelta(days=1)

    scheduled: Dict[str, dict] = {}
    explicit = 0
    for task in _topological(tasks):
        task_id = str(task.get("id"))
        stage_id = _lane_of(task, stages)
        if stage_id is None:
            continue
        hours = _task_hours(task)
        duration = _duration(hours, hours_per_day)
        start = stage_start.get(stage_id, today)
        if task_id in done_dates:
            end = done_dates[task_id]
            start = end - dt.timedelta(days=max(0, duration - 1))
        else:
            explicit_start = _date(task.get("planned_start"))
            explicit_target = _date(task.get("target"))
            if explicit_start:
                start = explicit_start
                explicit += 1
                end = explicit_target or (start + dt.timedelta(days=duration - 1))
            elif explicit_target:
                end = explicit_target
                start = end - dt.timedelta(days=max(0, duration - 1))
                explicit += 1
            else:
                for dependency in task.get("depends_on") or []:
                    if isinstance(dependency, str) and dependency in scheduled:
                        start = max(start, scheduled[dependency]["_end"] + dt.timedelta(days=1))
                start = max(start, stage_start.get(stage_id, today))
                end = start + dt.timedelta(days=duration - 1)
        if end < start:
            end = start
        scheduled[task_id] = {
            "id": task_id,
            "title": task.get("title"),
            "status": task.get("status"),
            "stage": stage_id,
            "package": task.get("package"),
            "labels": task.get("labels") or [],
            "depends_on": task.get("depends_on") or [],
            "estimate_hours": _number(task.get("estimate_hours")),
            "hours": round(hours, 2),
            "start": start,
            "end": end,
            "explicit": bool(task.get("planned_start") or task.get("target")),
            "overdue": bool(_date(task.get("target")) and _date(task.get("target")) < today
                            and task.get("status") != "done"),
            "_start": start,
            "_end": end,
        }
        lane = stage_start.get(stage_id, today)
        stage_start[stage_id] = min(stage_start.get(stage_id, start), start)
        stage_end[stage_id] = max(stage_end.get(stage_id, end), end)

    # Critical path: the dependency chain that ends last.
    critical: List[str] = []
    if scheduled:
        last = max(scheduled.values(), key=lambda row: (row["_end"], row["_start"]))
        current = last
        while current is not None:
            critical.append(current["id"])
            predecessors = [scheduled[dep] for dep in current["depends_on"]
                            if dep in scheduled and scheduled[dep]["_end"] < current["_start"]]
            current = max(predecessors, key=lambda row: row["_end"]) if predecessors else None
        critical.reverse()
    critical_set = set(critical)

    for row in scheduled.values():
        row["critical"] = row["id"] in critical_set

    overall_start = min([row["_start"] for row in scheduled.values()] + [today])
    overall_end = max([row["_end"] for row in scheduled.values()] + [today])
    days: List[dict] = []
    current = overall_start
    while current <= overall_end and len(days) < MAX_DAYS:
        iso = current.isocalendar()
        days.append({"date": current.isoformat(), "weekday": current.weekday(),
                     "week": f"{iso[0]}-W{iso[1]:02d}", "today": current == today})
        current += dt.timedelta(days=1)
    weeks: List[dict] = []
    seen = set()
    for day in days:
        week = day["week"]
        if week in seen:
            continue
        seen.add(week)
        weeks.append({"week": week, "start": day["date"]})

    lanes: List[dict] = []
    for stage in stages:
        stage_id = str(stage.get("id") or "")
        rows = sorted([row for row in scheduled.values() if row["stage"] == stage_id],
                      key=lambda row: (row["_start"], row["id"]))
        counts: Dict[str, int] = {}
        for task in tasks:
            if _lane_of(task, stages) == stage_id:
                counts[str(task.get("status") or "?")] = counts.get(str(task.get("status") or "?"), 0) + 1
        total = sum(counts.values())
        done = counts.get("done", 0)
        lanes.append({
            "id": stage_id,
            "title": stage.get("title") or stage_id or "All tasks",
            "goal": stage.get("goal"),
            "index": stage_index.get(stage_id, 0) + 1,
            "owner_decision": stage.get("owner_decision"),
            "exit_gates": [gate for gate in stage.get("exit_gates") or [] if isinstance(gate, str)],
            "start": _iso(stage_start.get(stage_id)),
            "end": _iso(stage_end.get(stage_id)),
            "tasks": [{
                **{key: value for key, value in row.items()
                   if not key.startswith("_") and key not in ("start", "end")},
                "start": row["start"].isoformat(),
                "end": row["end"].isoformat(),
            } for row in rows],
            "counts": counts,
            "progress": round(done / total, 3) if total else 0.0,
        })

    unscheduled = [task for task in tasks
                   if _lane_of(task, stages) is None
                   or str(task.get("id")) not in scheduled]
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "hours_per_day": hours_per_day,
        "start": overall_start.isoformat(),
        "end": overall_end.isoformat(),
        "days": days,
        "weeks": weeks,
        "stages": lanes,
        "critical_path": critical,
        "unscheduled": [str(task.get("id")) for task in unscheduled],
        "totals": {
            "tasks": len(tasks),
            "scheduled": len(scheduled),
            "days": len(days),
            "hours": round(sum(row["hours"] for row in scheduled.values()), 1),
            "explicit": explicit,
            "critical_path_tasks": len(critical),
        },
    }
