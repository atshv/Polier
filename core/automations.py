"""Deterministic automations (2.4): rules that turn project state into suggestions.

Rules are committed in ``automations.json`` and evaluated on demand — there is
no background daemon and no hidden write. Evaluation is a **dry run**: it returns
the matched rules with their suggested actions; the dashboard applies a suggestion
only when the owner confirms it through the normal API (state transition, session
start), and every such change keeps its audit trail.

Rule shape::

    {"version": 1, "rules": [
      {"id": "gate-failed", "name": "Failed gate needs attention", "enabled": true,
       "when": {"kind": "gate_failed"},
       "actions": [{"type": "state", "status": "blocked", "note": "Gate failed; fix it first."},
                   {"type": "open"}]}
    ]}

Kinds: ``gate_failed``, ``task_blocked`` (min_days), ``budget_over`` (level),
``review_ready``, ``session_failed`` (max_age_days), ``intake_proposed``
(min_age_days), ``stage_decision_pending``, ``task_ready``.
Actions: ``state`` (status/note suggestion), ``session`` (role/note suggestion),
``open`` (navigation hint), ``note`` (display text).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import dashboard as dashboard_mod
from . import evidence as evidence_mod
from . import intake as intake_mod
from . import runs as runs_mod
from . import worklog as worklog_mod
from .errors import PolierError
from .runs import FileLock

FILE = "automations.json"
VERSION = 1
ID = re.compile(r"^[a-z][a-z0-9-]{0,40}$")
KINDS = ("gate_failed", "task_blocked", "budget_over", "review_ready",
         "session_failed", "intake_proposed", "stage_decision_pending", "task_ready")
ACTION_TYPES = ("state", "session", "open", "note")
STATUSES = ("pending", "claimed", "in_progress", "verifying", "review", "rework",
            "blocked", "failed", "done")
BAD_GATE_RESULTS = frozenset({"fail", "infra", "busy", "timeout"})
TOP_FIELDS = frozenset({"version", "rules"})
RULE_FIELDS = frozenset({"id", "name", "description", "enabled", "when", "actions"})
WHEN_FIELDS = frozenset({"kind", "params"})
ACTION_FIELDS = frozenset({"type", "status", "note", "role", "text", "view"})


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _date(value: Any) -> Optional[dt.date]:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        return None


def path(root) -> Path:
    return Path(root) / FILE


def defaults() -> Dict[str, Any]:
    return {"version": VERSION, "rules": []}


def errors(value: Dict[str, Any]) -> List[str]:
    if not isinstance(value, dict):
        return ["automations.json must be an object"]
    found: List[str] = []
    for field in sorted(set(value) - TOP_FIELDS):
        found.append(f"automations: unknown field {field!r}")
    if value.get("version") != VERSION:
        found.append(f"automations: version must be {VERSION}")
    rules = value.get("rules")
    if not isinstance(rules, list):
        return found + ["automations: rules must be an array"]
    seen = set()
    for index, rule in enumerate(rules):
        label = f"automations: rule {index + 1}"
        if not isinstance(rule, dict):
            found.append(f"{label} must be an object")
            continue
        for field in sorted(set(rule) - RULE_FIELDS):
            found.append(f"{label}: unknown field {field!r}")
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not ID.match(rule_id):
            found.append(f"{label}: id must be lowercase (a-z, 0-9, '-')")
        elif rule_id in seen:
            found.append(f"{label}: duplicate id {rule_id!r}")
        else:
            seen.add(rule_id)
        name = rule.get("name")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            found.append(f"{label}: name must be 1–120 characters")
        if "enabled" in rule and not isinstance(rule["enabled"], bool):
            found.append(f"{label}: enabled must be true or false")
        when = rule.get("when")
        if not isinstance(when, dict):
            found.append(f"{label}: when must be an object")
        else:
            for field in sorted(set(when) - WHEN_FIELDS):
                found.append(f"{label}: when has unknown field {field!r}")
            if when.get("kind") not in KINDS:
                found.append(f"{label}: when.kind must be one of {', '.join(KINDS)}")
            if "params" in when and not isinstance(when["params"], dict):
                found.append(f"{label}: when.params must be an object")
        actions = rule.get("actions")
        if not isinstance(actions, list) or not actions:
            found.append(f"{label}: actions must be a non-empty array")
            continue
        for action in actions:
            if not isinstance(action, dict):
                found.append(f"{label}: every action must be an object")
                continue
            for field in sorted(set(action) - ACTION_FIELDS):
                found.append(f"{label}: action has unknown field {field!r}")
            if action.get("type") not in ACTION_TYPES:
                found.append(f"{label}: action.type must be one of {', '.join(ACTION_TYPES)}")
            if action.get("type") == "state" and action.get("status") not in STATUSES:
                found.append(f"{label}: state action needs a known status")
            if action.get("type") == "session" and not isinstance(action.get("role"), str):
                found.append(f"{label}: session action needs a role")
    return found


def load(root, strict: bool = False) -> Dict[str, Any]:
    value = defaults()
    target = path(root)
    if not target.is_file():
        return value
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        if strict:
            raise PolierError(f"cannot read {FILE}: {exc}") from exc
        return value
    if not isinstance(raw, dict):
        if strict:
            raise PolierError(f"{FILE} must be an object")
        return value
    value.update(raw)
    problems = errors(value)
    if problems and strict:
        raise PolierError("; ".join(problems))
    return value


def save(root, value: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(root).resolve()
    merged = defaults()
    merged.update(value or {})
    problems = errors(merged)
    if problems:
        raise PolierError("; ".join(problems))
    target = path(root)
    with FileLock(root / (FILE + ".lock")):
        temporary = target.with_name(f"{target.name}.{os.getpid()}.{time.time_ns()}.tmp")
        temporary.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(temporary, target)
    return merged


# -- evaluation -------------------------------------------------------------

def _bad_gate_events(root: Path) -> List[Dict[str, Any]]:
    latest: Dict[tuple, dict] = {}
    for record in evidence_mod.gate_records(root):
        task, gate = record.get("task"), record.get("gate")
        if not isinstance(task, str) or not isinstance(gate, str):
            continue
        previous = latest.get((task, gate))
        if previous is None or str(record.get("started") or "") > str(previous.get("started") or ""):
            latest[(task, gate)] = record
    events = []
    for (task, gate), record in latest.items():
        if record.get("result") in BAD_GATE_RESULTS or record.get("exit_code") not in (0, None):
            events.append({"kind": "gate_failed", "task": task, "gate": gate,
                           "detail": f"gate {gate} {record.get('result')}",
                           "at": record.get("finished") or record.get("started"),
                           "record": record.get("log")})
    return events


def _blocked_events(root: Path, tasks: List[dict], min_days: float) -> List[Dict[str, Any]]:
    events = []
    today = dt.date.today()
    for task in tasks:
        if task.get("status") != "blocked":
            continue
        task_id = str(task.get("id"))
        latest = None
        try:
            record = runs_mod.load_run(root, task_id)
        except Exception:  # noqa: BLE001
            record = {}
        for event in record.get("events") or []:
            if not isinstance(event, dict) or event.get("kind") != "state":
                continue
            if (event.get("data") or {}).get("to") == "blocked":
                day = _date(event.get("at"))
                if day and (latest is None or day > latest):
                    latest = day
        days = (today - latest).days if latest else 0
        if days >= float(min_days):
            events.append({"kind": "task_blocked", "task": task_id,
                           "detail": f"blocked for {days} day(s)", "at": latest.isoformat() if latest else None,
                           "days": days})
    return events


def _budget_events(tasks: List[dict], level: str) -> List[Dict[str, Any]]:
    events = []
    for task in tasks:
        budget = task.get("budget") or {}
        if level == "warn" and (budget.get("warn") or budget.get("over")):
            events.append({"kind": "budget_over", "task": task.get("id"),
                           "detail": "budget warning", "at": (task.get("run") or {}).get("updated")})
        elif level == "over" and budget.get("over"):
            events.append({"kind": "budget_over", "task": task.get("id"),
                           "detail": "budget exceeded", "at": (task.get("run") or {}).get("updated")})
    return events


def _review_events(tasks: List[dict]) -> List[Dict[str, Any]]:
    return [{"kind": "review_ready", "task": task.get("id"),
             "detail": "review pending", "at": (task.get("run") or {}).get("updated")}
            for task in tasks if task.get("status") in ("review", "verifying")
            and not (task.get("review") or {}).get("verdict")]


def _session_events(root: Path, max_age_days: float) -> List[Dict[str, Any]]:
    today = dt.date.today()
    events = []
    for session in worklog_mod.session_records(root):
        if session.get("status") != "failed":
            continue
        day = _date(session.get("ended") or session.get("started"))
        if day and (today - day).days > max_age_days:
            continue
        events.append({"kind": "session_failed", "task": session.get("task"),
                       "detail": f"session {session.get('id')} failed", "at": session.get("ended"),
                       "session": session.get("id")})
    return events


def _intake_events(root: Path, min_age_days: float) -> List[Dict[str, Any]]:
    today = dt.date.today()
    events = []
    for entry in intake_mod.load_all(root, "proposed"):
        day = _date(entry.get("created"))
        age = (today - day).days if day else 0
        if age >= float(min_age_days):
            events.append({"kind": "intake_proposed", "task": None,
                           "detail": f"{entry.get('id')} proposed {age} day(s) ago",
                           "at": entry.get("created"), "intake": entry.get("id")})
    return events


def _stage_events(snapshot: dict) -> List[Dict[str, Any]]:
    events = []
    for stage in snapshot.get("stages") or []:
        # A stage is ready for the owner decision when its tasks are done and its
        # exit gates have records; the stage report marks it complete only after
        # the decision, so use the raw facts here.
        if stage.get("tasks_open") or stage.get("missing_gates"):
            continue
        if stage.get("owner_decision") == "pending":
            events.append({"kind": "stage_decision_pending", "task": None,
                           "detail": f"stage {stage.get('id')} is ready but its owner decision is pending",
                           "at": None, "stage": stage.get("id")})
    return events


def _ready_events(tasks: List[dict]) -> List[Dict[str, Any]]:
    return [{"kind": "task_ready", "task": task.get("id"), "detail": "ready now",
             "at": (task.get("run") or {}).get("updated")}
            for task in tasks if task.get("ready") and task.get("wave") == 0]


def evaluate(root, *, snapshot: Optional[dict] = None,
             settings: Optional[dict] = None) -> Dict[str, Any]:
    """Dry-run evaluation: matched rules with their suggested actions."""
    root = Path(root).resolve()
    value = load(root, strict=True)
    snapshot = snapshot if snapshot is not None else dashboard_mod.snapshot(root)
    tasks = snapshot.get("tasks") or []
    events_by_kind: Dict[str, List[Dict[str, Any]]] = {}
    for kind in KINDS:
        params: Dict[str, Any] = {}
        events: List[Dict[str, Any]] = []
        if kind == "gate_failed":
            events = _bad_gate_events(root)
        elif kind == "task_blocked":
            events = _blocked_events(root, tasks, 0)
        elif kind == "budget_over":
            events = _budget_events(tasks, "over")
        elif kind == "review_ready":
            events = _review_events(tasks)
        elif kind == "session_failed":
            events = _session_events(root, 30)
        elif kind == "intake_proposed":
            events = _intake_events(root, 0)
        elif kind == "stage_decision_pending":
            events = _stage_events(snapshot)
        elif kind == "task_ready":
            events = _ready_events(tasks)
        events_by_kind[kind] = events
    matches: List[Dict[str, Any]] = []
    for rule in value.get("rules") or []:
        if not isinstance(rule, dict) or rule.get("enabled") is False:
            continue
        when = rule.get("when") or {}
        kind = when.get("kind")
        params = when.get("params") or {}
        events = list(events_by_kind.get(str(kind), []))
        if kind == "task_blocked":
            min_days = params.get("min_days", 0)
            events = _blocked_events(root, tasks, float(min_days))
        elif kind == "budget_over":
            events = _budget_events(tasks, str(params.get("level") or "over"))
        elif kind == "session_failed":
            events = _session_events(root, float(params.get("max_age_days", 30)))
        elif kind == "intake_proposed":
            events = _intake_events(root, float(params.get("min_age_days", 0)))
        for event in events:
            key = f"{rule.get('id')}:{kind}:{event.get('task') or event.get('stage') or event.get('intake') or event.get('session') or event.get('gate')}"
            matches.append({"rule": rule.get("id"), "name": rule.get("name"),
                            "enabled": rule.get("enabled", True), "event": event,
                            "actions": rule.get("actions") or [], "key": key})
    return {"generated_at": _now(), "dry_run": True,
            "rules": [{"id": rule.get("id"), "name": rule.get("name"),
                       "enabled": rule.get("enabled", True)} for rule in value.get("rules") or []],
            "matches": matches, "total": len(matches)}
