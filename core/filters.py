"""Structured task filters and grouping (2.1).

The dashboard's filter builder composes conditions as
``{"field": ..., "op": ..., "value": ...}`` and the server applies them to the
task views from ``core.dashboard``. There is deliberately no query language:
the board model is small, and a bounded operator set stays explainable, saved
in ``views/*.json`` and testable.

Fields are derived task-view attributes (``ready``, ``running``, ``budget`` …),
not board fields, so filtering never changes the project files.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .errors import PolierError

FIELDS: Dict[str, str] = {
    "id": "text",
    "title": "text",
    "status": "status",
    "stage": "text",
    "stage_title": "text",
    "package": "text",
    "owner": "text",
    "label": "label",
    "complexity": "number",
    "estimate_hours": "number",
    "tokens": "number",
    "attempt": "number",
    "gates_missing": "number",
    "ready": "bool",
    "running": "bool",
    "claimed": "bool",
    "blocked": "bool",
    "review_verdict": "text",
    "budget": "budget",
}

OPERATORS: Dict[str, List[str]] = {
    "text": ["is", "is_not", "contains", "not_contains", "empty", "not_empty"],
    "status": ["is", "is_not", "any_of", "none_of"],
    "label": ["any_of", "none_of", "empty", "not_empty"],
    "number": ["eq", "neq", "gt", "gte", "lt", "lte", "empty", "not_empty"],
    "bool": ["is"],
    "budget": ["is"],
}

NO_VALUE = ("empty", "not_empty")
GROUP_BY = (None, "status", "stage", "package", "owner", "label")
SORTABLE = ("id", "title", "status", "stage", "package", "owner", "complexity",
            "estimate_hours", "tokens", "attempt", "gates_missing")
STATUS_ORDER = ("pending", "claimed", "in_progress", "verifying", "review", "rework",
                "blocked", "failed", "done")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _labels(task: dict) -> List[str]:
    value = task.get("labels")
    return [entry for entry in value if isinstance(entry, str)] if isinstance(value, list) else []


def _budget_state(task: dict) -> str:
    budget = task.get("budget") if isinstance(task.get("budget"), dict) else {}
    if budget.get("over"):
        return "over"
    if budget.get("warn"):
        return "warn"
    return "ok"


def value_of(task: dict, field: str) -> Any:
    """The value a filter compares for one task view."""
    if field == "label":
        return _labels(task)
    if field == "ready":
        return bool(task.get("ready"))
    if field == "running":
        return bool(task.get("running"))
    if field == "claimed":
        return bool(task.get("claim"))
    if field == "blocked":
        return task.get("status") == "blocked" or bool(task.get("blocked_reason"))
    if field == "budget":
        return _budget_state(task)
    if field == "review_verdict":
        review = task.get("review") if isinstance(task.get("review"), dict) else {}
        return _text(review.get("verdict"))
    if field in ("estimate_hours",):
        value = task.get(field)
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    if field in ("tokens", "attempt", "gates_missing"):
        value = task.get(field)
        if field == "gates_missing" and value is None:
            value = len(task.get("gates_missing") or [])
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0
    if field == "complexity":
        value = task.get(field)
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    return _text(task.get(field))


def _value_problem(field: str, op: str, value: Any) -> Optional[str]:
    kind = FIELDS[field]
    if op in NO_VALUE:
        if value not in (None, "", []):
            return f"operator {op!r} takes no value"
        return None
    if kind == "bool":
        return None if isinstance(value, bool) else "value must be true or false"
    if kind == "number":
        return None if isinstance(value, (int, float)) and not isinstance(value, bool) \
            else "value must be a number"
    if kind == "status":
        allowed = set(STATUS_ORDER)
        if op in ("any_of", "none_of"):
            if not isinstance(value, list) or not value or any(item not in allowed for item in value):
                return "value must be a list of statuses"
            return None
        return None if value in allowed else "value must be a status"
    if kind == "budget":
        return None if value in ("over", "warn", "ok") else "value must be over, warn or ok"
    if kind == "label":
        if op in ("any_of", "none_of"):
            if not isinstance(value, list) or not value or any(not isinstance(item, str) for item in value):
                return "value must be a list of label ids"
            return None
        return None
    if op in ("any_of", "none_of"):
        return "this operator takes a list" if not isinstance(value, list) else None
    return None if (value is None or isinstance(value, str)) else "value must be text"


def validate(filters: Any) -> List[str]:
    """Validation errors of a filter list ([] when valid)."""
    if filters is None:
        return []
    if not isinstance(filters, list):
        return ["filters must be an array"]
    found: List[str] = []
    for index, condition in enumerate(filters):
        label = f"filter {index + 1}"
        if not isinstance(condition, dict):
            found.append(f"{label}: must be an object")
            continue
        unknown = set(condition) - {"field", "op", "value"}
        if unknown:
            found.append(f"{label}: unknown field(s) {', '.join(sorted(unknown))}")
        field, op = condition.get("field"), condition.get("op")
        if field not in FIELDS:
            found.append(f"{label}: unknown field {field!r}")
            continue
        if op not in OPERATORS[FIELDS[field]]:
            found.append(f"{label}: operator {op!r} is not allowed for {field!r}")
            continue
        problem = _value_problem(field, op, condition.get("value"))
        if problem:
            found.append(f"{label}: {problem}")
    return found


def _matches(task: dict, condition: dict) -> bool:
    field, op = condition["field"], condition["op"]
    value = value_of(task, field)
    expected = condition.get("value")
    if op == "empty":
        return value in (None, "", [])
    if op == "not_empty":
        return value not in (None, "", [])
    if field == "label":
        labels = value if isinstance(value, list) else []
        if op == "any_of":
            return any(label in labels for label in expected)
        if op == "none_of":
            return not any(label in labels for label in expected)
        return False
    if FIELDS[field] == "bool":
        return bool(value) is bool(expected)
    if FIELDS[field] == "number":
        if value is None:
            return False
        expected = float(expected)
        actual = float(value)
        return {
            "eq": actual == expected, "neq": actual != expected,
            "gt": actual > expected, "gte": actual >= expected,
            "lt": actual < expected, "lte": actual <= expected,
        }[op]
    if op in ("any_of", "none_of"):
        items = [str(item).lower() for item in expected]
        actual = str(value or "").lower()
        return (actual in items) if op == "any_of" else (actual not in items)
    if op == "is":
        return str(value or "").lower() == str(expected or "").lower()
    if op == "is_not":
        return str(value or "").lower() != str(expected or "").lower()
    if op == "contains":
        return str(expected or "").lower() in str(value or "").lower()
    if op == "not_contains":
        return str(expected or "").lower() not in str(value or "").lower()
    return False


def apply(filters: Optional[List[dict]], tasks: Iterable[dict]) -> List[dict]:
    """Tasks that match every condition (AND). An invalid list raises."""
    problems = validate(filters)
    if problems:
        raise PolierError("; ".join(problems))
    conditions = filters or []
    return [task for task in tasks if all(_matches(task, condition) for condition in conditions)]


def group(tasks: List[dict], field: Optional[str]) -> List[Dict[str, Any]]:
    """Group tasks by a field; the order follows the canonical status order or first appearance."""
    if not field:
        return [{"key": "all", "label": "All", "tasks": tasks}]
    if field not in GROUP_BY:
        raise PolierError(f"cannot group by {field!r}")
    buckets: Dict[str, List[dict]] = {}
    for task in tasks:
        if field == "label":
            labels = _labels(task) or ["(none)"]
            for label in labels:
                buckets.setdefault(label, []).append(task)
        else:
            key = _text(value_of(task, field)) or "(none)"
            buckets.setdefault(key, []).append(task)
    if field == "status":
        order = [status for status in STATUS_ORDER if status in buckets]
        order += [key for key in buckets if key not in order]
    else:
        order = list(buckets)  # first appearance in board/view order
    return [{"key": key, "label": key, "tasks": buckets[key]} for key in order]


def sort(tasks: List[dict], field: str = "id", direction: str = "asc") -> List[dict]:
    """Stable sort by a task-view field; missing values go last."""
    if field not in SORTABLE:
        raise PolierError(f"cannot sort by {field!r}")
    reverse = direction == "desc"

    def key(task: dict):
        value = value_of(task, field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return (1, float(value), "")
        return (0 if value not in (None, "") else 1, 0.0, str(value or "").lower())

    return sorted(tasks, key=key, reverse=reverse)


def builtin_views(me: Optional[str] = None) -> List[Dict[str, Any]]:
    """Ready-made views the dashboard offers before anything is saved."""
    base = {"kind": "board", "builtin": True, "group_by": "status",
            "sort": {"field": "id", "dir": "asc"}, "filters": []}
    views = [
        {**base, "id": "all", "name": "All tasks", "group_by": "status"},
        {**base, "id": "ready", "name": "Ready now",
         "filters": [{"field": "ready", "op": "is", "value": True}], "group_by": "stage"},
        {**base, "id": "blocked", "name": "Blocked",
         "filters": [{"field": "blocked", "op": "is", "value": True}], "group_by": "stage"},
        {**base, "id": "review", "name": "Review queue", "kind": "table",
         "filters": [{"field": "status", "op": "any_of", "value": ["review", "verifying"]}],
         "group_by": "owner"},
        {**base, "id": "over-budget", "name": "Over budget", "kind": "table",
         "filters": [{"field": "budget", "op": "is", "value": "over"}], "group_by": None},
        {**base, "id": "unestimated", "name": "No estimate", "kind": "table",
         "filters": [{"field": "estimate_hours", "op": "empty"}], "group_by": "stage"},
    ]
    if me:
        views.insert(1, {**base, "id": "mine", "name": f"Mine ({me})",
                         "filters": [{"field": "owner", "op": "is", "value": me}],
                         "group_by": "stage"})
    return views
