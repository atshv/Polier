"""Plan editing for the dashboard (2.0): tasks, dependencies and stage decisions.

The board is the plan of record and stays readable/writable by every CLI tool.
Edits therefore follow the same rules as ``core/state.py``: change the loaded
dict, validate it with ``core.board.board_errors``, write atomically under
``board.json.lock`` and refuse anything that would create a dependency cycle.

Status changes are *not* plan edits. They go through ``core.state.set_status``
(``POST /api/tasks/<id>/state``) so attempts, gates, reviews and approvals keep
their checkpoints.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import board as board_mod
from .errors import PolierError
from .runs import FileLock

BOARD = "board.json"
ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{0,5}-[0-9]{2,3}$")
EDITABLE = frozenset({
    "title", "goal", "why", "satisfies", "depends_on", "complexity", "stage",
    "parallel_group", "scope_write", "scope_read", "acceptance", "gates",
    "owner", "branch", "worktree", "scope_write_forbidden", "package",
    "exclusive", "resources",
})
REQUIRED_EDIT = ("title", "goal", "scope_write", "acceptance", "gates")
MAX_TEXT = 20_000


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _strings(value: Any, field: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise PolierError(f"{field} must be a list of strings")
    return [item.strip() for item in value if item.strip()]


def _write_board(root: Path, board: dict) -> None:
    path = root / BOARD
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temporary.write_text(json.dumps(board, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _load(root: Path) -> dict:
    board = board_mod.load_board(root)
    if board is None:
        raise PolierError(f"no board.json at {root}")
    return board


def _validate(root: Path, board: dict) -> None:
    errors = board_mod.board_errors(board)
    if errors:
        raise PolierError("board would be invalid: " + "; ".join(errors))
    cycle = dependency_cycle(board)
    if cycle:
        raise PolierError("dependency cycle: " + " -> ".join(cycle))


def dependency_cycle(board: dict) -> Optional[List[str]]:
    tasks = {str(task.get("id")): task for task in board.get("tasks", []) if isinstance(task, dict)}
    state: Dict[str, int] = {}

    def visit(task_id: str, stack: List[str]) -> Optional[List[str]]:
        if state.get(task_id) == 2:
            return None
        if state.get(task_id) == 1:
            return stack[stack.index(task_id):] + [task_id] if task_id in stack else [task_id]
        state[task_id] = 1
        task = tasks.get(task_id) or {}
        for dependency in task.get("depends_on") or []:
            if isinstance(dependency, str) and dependency in tasks:
                found = visit(dependency, stack + [task_id])
                if found:
                    return found
        state[task_id] = 2
        return None

    for task_id in tasks:
        found = visit(task_id, [])
        if found:
            return found
    return None


def suggest_id(board: dict, prefix: Optional[str] = None) -> str:
    """The next free ``<PREFIX>-NN`` for a new task."""
    used = {str(task.get("id")) for task in board.get("tasks", []) if isinstance(task, dict)}
    if prefix:
        clean = re.sub(r"[^A-Z0-9]", "", prefix.upper())[:6] or "T"
    else:
        clean = "T"
    for number in range(1, 1000):
        candidate = f"{clean}-{number:02d}"
        if candidate not in used:
            return candidate
    raise PolierError("no free task ID in that range")


def _task(board: dict, task_id: str) -> dict:
    for entry in board.get("tasks", []):
        if isinstance(entry, dict) and entry.get("id") == task_id:
            return entry
    raise KeyError(task_id)


def _apply_payload(board: dict, task: dict, payload: dict, *, creating: bool) -> dict:
    """Validate and copy the editable fields of `payload` onto `task`."""
    if not isinstance(payload, dict):
        raise PolierError("payload must be an object")
    for key in payload:
        if key not in EDITABLE:
            raise PolierError(f"field '{key}' is not editable in the plan editor")
    for field in ("title", "goal"):
        if field in payload:
            value = _text(payload[field])
            if not value:
                raise PolierError(f"{field} must not be empty")
            if len(value) > MAX_TEXT:
                raise PolierError(f"{field} is too long")
            task[field] = value
    for field in ("why",):
        if field in payload:
            task[field] = _text(payload[field]) or None
    for field in ("scope_write", "scope_read", "acceptance", "gates", "satisfies",
                  "depends_on", "scope_write_forbidden"):
        if field in payload:
            task[field] = _strings(payload[field], field)
    if "complexity" in payload:
        value = payload["complexity"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 1 or value > 10:
            raise PolierError("complexity must be a number between 1 and 10")
        task["complexity"] = value
    if "stage" in payload:
        stage = _text(payload["stage"])
        if stage and stage not in board_mod.stage_ids(board):
            raise PolierError(f"unknown stage '{stage}'")
        task["stage"] = stage or task.get("stage")
    if "parallel_group" in payload:
        task["parallel_group"] = _text(payload["parallel_group"]) or None
    if "package" in payload:
        task["package"] = _text(payload["package"]) or None
    if "exclusive" in payload:
        task["exclusive"] = _strings(payload["exclusive"], "exclusive")
    if "resources" in payload:
        value = payload["resources"]
        if value is not None and not isinstance(value, dict):
            raise PolierError("resources must be an object")
        task["resources"] = value
    if creating:
        for field in REQUIRED_EDIT:
            if field not in payload or (field not in ("scope_write", "acceptance", "gates")
                                        and not _text(payload.get(field))):
                raise PolierError(f"{field} is required")
        for field in ("scope_write", "acceptance", "gates"):
            if field not in payload or not isinstance(payload[field], list):
                raise PolierError(f"{field} is required")
    return task


def create_task(root, payload: dict) -> dict:
    root = Path(root).resolve()
    with FileLock(root / (BOARD + ".lock")):
        board = _load(root)
        payload = dict(payload)
        explicit_id = _text(payload.pop("id", ""))
        prefix = _text(payload.pop("prefix", ""))
        task_id = explicit_id or suggest_id(board, prefix)
        if not ID_PATTERN.fullmatch(task_id):
            raise PolierError("task ID must look like 'T-01' or 'DASH-01'")
        if any(isinstance(task, dict) and task.get("id") == task_id for task in board.get("tasks", [])):
            raise PolierError(f"task {task_id} already exists")
        task: Dict[str, Any] = {
            "id": task_id,
            "title": "",
            "goal": "",
            "why": None,
            "satisfies": [],
            "status": "pending",
            "depends_on": [],
            "complexity": 2,
            "stage": _text(payload.get("stage")) or (board.get("stages") or [{}])[0].get("id", "foundation"),
            "parallel_group": None,
            "scope_write": [],
            "scope_read": [],
            "acceptance": [],
            "gates": [],
            "owner": None,
            "branch": f"task/{task_id}",
            "worktree": None,
            "round": 0,
            "evidence": [],
            "scope_write_forbidden": [],
        }
        _apply_payload(board, task, payload, creating=True)
        board.setdefault("tasks", []).append(task)
        _validate(root, board)
        _write_board(root, board)
        return task


def update_task(root, task_id: str, payload: dict) -> dict:
    root = Path(root).resolve()
    with FileLock(root / (BOARD + ".lock")):
        board = _load(root)
        task = _task(board, task_id)
        if task.get("status") == "done":
            raise PolierError("a done task is reopened through the state API before its plan is edited")
        _apply_payload(board, task, payload, creating=False)
        _validate(root, board)
        _write_board(root, board)
        return task


def delete_task(root, task_id: str) -> dict:
    root = Path(root).resolve()
    with FileLock(root / (BOARD + ".lock")):
        board = _load(root)
        task = _task(board, task_id)
        if task.get("status") not in ("pending", "blocked", "failed"):
            raise PolierError("only pending, blocked or failed tasks can be deleted")
        dependents = [
            str(other.get("id")) for other in board.get("tasks", [])
            if isinstance(other, dict) and task_id in (other.get("depends_on") or [])
        ]
        if dependents:
            raise PolierError("still needed by: " + ", ".join(dependents))
        board["tasks"] = [entry for entry in board.get("tasks", [])
                          if not (isinstance(entry, dict) and entry.get("id") == task_id)]
        _validate(root, board)
        _write_board(root, board)
        return {"id": task_id, "deleted": True}


def set_stage_decision(root, stage_id: str, decision: str) -> dict:
    root = Path(root).resolve()
    if decision not in board_mod.OWNER_DECISIONS:
        raise PolierError(f"decision must be one of {sorted(board_mod.OWNER_DECISIONS)}")
    with FileLock(root / (BOARD + ".lock")):
        board = _load(root)
        stage = next((entry for entry in board.get("stages", [])
                      if isinstance(entry, dict) and entry.get("id") == stage_id), None)
        if stage is None:
            raise KeyError(stage_id)
        stage["owner_decision"] = decision
        _validate(root, board)
        _write_board(root, board)
        return stage


def move_stage(root, stage_id: str, delta: int) -> dict:
    """Reorder stages by `delta` places (the board lists them in run order)."""
    root = Path(root).resolve()
    with FileLock(root / (BOARD + ".lock")):
        board = _load(root)
        stages = board.get("stages") or []
        index = next((position for position, stage in enumerate(stages)
                      if isinstance(stage, dict) and stage.get("id") == stage_id), None)
        if index is None:
            raise KeyError(stage_id)
        target = max(0, min(len(stages) - 1, index + int(delta)))
        if target != index:
            stages.insert(target, stages.pop(index))
            _validate(root, board)
            _write_board(root, board)
        return {"stage": stage_id, "index": target}
