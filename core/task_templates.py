"""Task templates (2.3): reusable task shapes stored in the project.

A template is a small committed JSON file in ``templates/tasks/<id>.json`` with
the fields a task needs (scope, acceptance, gates, complexity, labels, estimate
and an optional goal/why). It is used when creating a task from the plan editor,
the CLI or an accepted intake proposal — it never bypasses validation: the
task is still created through ``core.plan_edit`` with the board schema check.

Templates can be written by hand or saved from an existing task ("save as
template"), which is the fastest way to keep a good structure.
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

DIR = "templates/tasks"
VERSION = 1
ID = re.compile(r"^[a-z][a-z0-9-]{0,40}$")
FIELDS = frozenset({
    "version", "id", "name", "title", "goal", "why", "stage", "package",
    "scope_write", "scope_read", "acceptance", "gates", "complexity",
    "labels", "estimate_hours", "owner", "exclusive", "parallel_group",
})
COPYABLE = ("title", "goal", "why", "stage", "package", "scope_write", "scope_read",
            "acceptance", "gates", "complexity", "labels", "estimate_hours",
            "owner", "exclusive", "parallel_group")


def folder(root) -> Path:
    return Path(root) / DIR


def _path(root, template_id: str) -> Path:
    if not ID.match(template_id or ""):
        raise PolierError("template id must be lowercase (a-z, 0-9, '-')")
    return folder(root) / f"{template_id}.json"


def errors(template: Dict[str, Any]) -> List[str]:
    if not isinstance(template, dict):
        return ["template must be an object"]
    found: List[str] = []
    for field in sorted(set(template) - FIELDS):
        found.append(f"template: unknown field {field!r}")
    if template.get("version") not in (None, VERSION):
        found.append(f"template: version must be {VERSION}")
    if not isinstance(template.get("id"), str) or not ID.match(template["id"]):
        found.append("template: id must be lowercase (a-z, 0-9, '-')")
    name = template.get("name")
    if name is not None and (not isinstance(name, str) or not 1 <= len(name.strip()) <= 80):
        found.append("template: name must be 1–80 characters")
    for field in ("scope_write", "scope_read", "acceptance", "gates", "labels", "exclusive"):
        if field in template and (not isinstance(template[field], list)
                                  or any(not isinstance(item, str) for item in template[field])):
            found.append(f"template: {field} must be a list of strings")
    if "complexity" in template:
        value = template["complexity"]
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
            found.append("template: complexity must be an integer 1–10")
    if "estimate_hours" in template:
        value = template["estimate_hours"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 10_000:
            found.append("template: estimate_hours must be a number 0–10000")
    for field in ("title", "goal", "why", "stage", "package", "owner", "parallel_group"):
        if field in template and template[field] is not None and not isinstance(template[field], str):
            found.append(f"template: {field} must be a string or null")
    return found


def load_all(root) -> List[Dict[str, Any]]:
    base = folder(root)
    if not base.is_dir():
        return []
    templates: List[Dict[str, Any]] = []
    for path in sorted(base.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(value, dict):
            continue
        value.setdefault("version", VERSION)
        value.setdefault("id", path.stem)
        value.setdefault("name", path.stem.replace("-", " ").title())
        if errors(value):
            continue
        templates.append(value)
    templates.sort(key=lambda template: str(template.get("name") or template.get("id")))
    return templates


def get(root, template_id: str) -> Dict[str, Any]:
    target = _path(root, template_id)
    if not target.is_file():
        raise KeyError(template_id)
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PolierError(f"template {template_id} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise PolierError(f"template {template_id} must be an object")
    value.setdefault("version", VERSION)
    value.setdefault("id", template_id)
    problems = errors(value)
    if problems:
        raise PolierError("; ".join(problems))
    return value


def save(root, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Write one template (validated, atomic)."""
    root = Path(root).resolve()
    template = dict(payload or {})
    template.setdefault("version", VERSION)
    template.setdefault("name", str(template.get("id") or "").replace("-", " ").title())
    problems = errors(template)
    if problems:
        raise PolierError("; ".join(problems))
    target = _path(root, str(template["id"]))
    target.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(target.parent / ".templates.lock"):
        temporary = target.with_name(f"{target.name}.{os.getpid()}.{time.time_ns()}.tmp")
        temporary.write_text(json.dumps(template, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
        os.replace(temporary, target)
    return template


def delete(root, template_id: str) -> Dict[str, Any]:
    root = Path(root).resolve()
    target = _path(root, template_id)
    with FileLock(target.parent / ".templates.lock"):
        if not target.is_file():
            raise KeyError(template_id)
        target.unlink()
    return {"id": template_id, "deleted": True}


def from_task(root, task_id: str, template_id: str, name: Optional[str] = None) -> Dict[str, Any]:
    """Save the reusable shape of an existing task as a template."""
    board = board_mod.load_board(Path(root).resolve(), strict=False)
    if board is None:
        raise PolierError("no board.json; cannot read a task")
    task = next((entry for entry in board.get("tasks") or []
                 if isinstance(entry, dict) and entry.get("id") == task_id), None)
    if task is None:
        raise KeyError(task_id)
    template: Dict[str, Any] = {
        "version": VERSION,
        "id": template_id,
        "name": name or f"From {task_id}",
    }
    for field in COPYABLE:
        if field in task and task[field] is not None:
            template[field] = task[field]
    template.pop("id", None)  # keep the id field from above, not the task id
    template["id"] = template_id
    return save(root, template)


def defaults(root, template_id: Optional[str]) -> Dict[str, Any]:
    """The task payload defaults of a template (without id/version/name)."""
    if not template_id:
        return {}
    template = get(root, template_id)
    return {field: template[field] for field in COPYABLE if field in template}
