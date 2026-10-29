"""Intake (2.3): proposals before they become work items.

An intake entry is a committed JSON file in ``intake/<id>.json`` with a tiny
lifecycle: ``proposed`` → ``accepted`` (creates a pending board task through
``core.plan_edit``) or ``rejected`` (with a reason). The point is triage: ideas,
bug reports and requests get a place to wait and a decision trail, instead of
jumping straight onto the plan.

The intake is deliberately small: title, description, kind, priority, source,
links and the decision. A task template (``templates/tasks/<id>.json``) can
provide the structural defaults when accepting; the board validation and the
dependency-cycle check still apply.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import plan_edit
from . import task_templates
from .errors import PolierError
from .runs import FileLock

DIR = "intake"
VERSION = 1
ID = re.compile(r"^IN-[0-9]{3,}$")
STATUSES = ("proposed", "accepted", "rejected")
KINDS = ("idea", "issue", "request", "question")
PRIORITIES = ("low", "medium", "high")
SOURCES = ("owner", "agent", "cli", "mcp", "web")
FIELDS = frozenset({
    "version", "id", "title", "description", "kind", "priority", "source",
    "status", "created", "created_by", "links", "task", "decision",
})
EDITABLE = frozenset({"title", "description", "kind", "priority", "links"})


def _now() -> str:
    return dt_now()


def dt_now():
    import datetime as dt

    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def folder(root) -> Path:
    return Path(root) / DIR


def _path(root, intake_id: str) -> Path:
    if not ID.match(intake_id or ""):
        raise PolierError("intake id must look like IN-001")
    return folder(root) / f"{intake_id}.json"


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def validate(entry: Dict[str, Any]) -> List[str]:
    if not isinstance(entry, dict):
        return ["intake entry must be an object"]
    found: List[str] = []
    for field in sorted(set(entry) - FIELDS):
        found.append(f"intake: unknown field {field!r}")
    if entry.get("version") not in (None, VERSION):
        found.append(f"intake: version must be {VERSION}")
    if not ID.match(str(entry.get("id") or "")):
        found.append("intake: id must look like IN-001")
    title = entry.get("title")
    if not isinstance(title, str) or not 3 <= len(title.strip()) <= 160:
        found.append("intake: title must be 3–160 characters")
    description = entry.get("description")
    if description is not None and (not isinstance(description, str) or len(description) > 20_000):
        found.append("intake: description must be a string of at most 20000 characters")
    if entry.get("kind", "idea") not in KINDS:
        found.append(f"intake: kind must be one of {', '.join(KINDS)}")
    if entry.get("priority", "medium") not in PRIORITIES:
        found.append(f"intake: priority must be one of {', '.join(PRIORITIES)}")
    if entry.get("source", "owner") not in SOURCES:
        found.append(f"intake: source must be one of {', '.join(SOURCES)}")
    if entry.get("status", "proposed") not in STATUSES:
        found.append(f"intake: status must be one of {', '.join(STATUSES)}")
    if "links" in entry and (not isinstance(entry["links"], list)
                            or any(not isinstance(item, str) for item in entry["links"])):
        found.append("intake: links must be a list of strings")
    decision = entry.get("decision")
    if decision is not None:
        if not isinstance(decision, dict):
            found.append("intake: decision must be an object")
        else:
            for field in sorted(set(decision) - {"by", "note", "at"}):
                found.append(f"intake: decision has unknown field {field!r}")
    return found


def allocate(root) -> str:
    highest = 0
    base = folder(root)
    if base.is_dir():
        for path in base.glob("IN-*.json"):
            match = re.fullmatch(r"IN-([0-9]{3,})", path.stem)
            if match:
                highest = max(highest, int(match.group(1)))
    return f"IN-{highest + 1:03d}"


def create(root, payload: Dict[str, Any], *, by: str = "owner",
           source: str = "owner") -> Dict[str, Any]:
    """Create a proposed entry (id allocated under a lock)."""
    root = Path(root).resolve()
    base = folder(root)
    base.mkdir(parents=True, exist_ok=True)
    with FileLock(base / ".intake.lock"):
        intake_id = allocate(root)
        entry = {
            "version": VERSION,
            "id": intake_id,
            "title": _text(payload.get("title")),
            "description": _text(payload.get("description")),
            "kind": str(payload.get("kind") or "idea"),
            "priority": str(payload.get("priority") or "medium"),
            "source": str(payload.get("source") or source),
            "status": "proposed",
            "created": dt_now(),
            "created_by": str(payload.get("created_by") or by),
            "links": [item for item in payload.get("links") or [] if isinstance(item, str)],
            "task": None,
            "decision": None,
        }
        problems = validate(entry)
        if problems:
            raise PolierError("; ".join(problems))
        target = base / f"{intake_id}.json"
        temporary = target.with_name(f"{target.name}.{os.getpid()}.{time.time_ns()}.tmp")
        temporary.write_text(json.dumps(entry, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
        os.replace(temporary, target)
    return entry


def load_all(root, status: Optional[str] = None) -> List[Dict[str, Any]]:
    base = folder(root)
    if not base.is_dir():
        return []
    entries: List[Dict[str, Any]] = []
    for path in sorted(base.glob("IN-*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(value, dict):
            continue
        value.setdefault("version", VERSION)
        value.setdefault("id", path.stem)
        value.setdefault("status", "proposed")
        if validate(value):
            continue
        if status and value.get("status") != status:
            continue
        entries.append(value)
    entries.sort(key=lambda entry: (0 if entry.get("status") == "proposed" else 1,
                                    str(entry.get("created") or "")))
    return entries


def get(root, intake_id: str) -> Dict[str, Any]:
    target = _path(root, intake_id)
    if not target.is_file():
        raise KeyError(intake_id)
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PolierError(f"intake {intake_id} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise PolierError(f"intake {intake_id} must be an object")
    value.setdefault("version", VERSION)
    value.setdefault("id", intake_id)
    value.setdefault("status", "proposed")
    return value


def _write(root, entry: Dict[str, Any]) -> Dict[str, Any]:
    problems = validate(entry)
    if problems:
        raise PolierError("; ".join(problems))
    target = _path(root, str(entry["id"]))
    temporary = target.with_name(f"{target.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temporary.write_text(json.dumps(entry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, target)
    return entry


def update(root, intake_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(root).resolve()
    base = folder(root)
    with FileLock(base / ".intake.lock"):
        entry = get(root, intake_id)
        if entry.get("status") != "proposed":
            raise PolierError("only proposed intake entries can be edited")
        for field in sorted(set(payload) - EDITABLE):
            raise PolierError(f"field {field!r} is not editable in intake")
        for field in EDITABLE:
            if field in payload:
                if field == "links":
                    if not isinstance(payload["links"], list):
                        raise PolierError("links must be a list")
                    entry["links"] = [item for item in payload["links"] if isinstance(item, str)]
                elif field in ("kind", "priority"):
                    entry[field] = str(payload[field])
                else:
                    entry[field] = _text(payload[field])
        return _write(root, entry)


def accept(root, intake_id: str, *, by: str = "owner", note: str = "",
           task_payload: Optional[Dict[str, Any]] = None,
           template: Optional[str] = None) -> Dict[str, Any]:
    """Accept a proposal and create its pending task."""
    root = Path(root).resolve()
    base = folder(root)
    with FileLock(base / ".intake.lock"):
        entry = get(root, intake_id)
        if entry.get("status") != "proposed":
            raise PolierError(f"intake {intake_id} is already {entry.get('status')}")
        defaults = task_templates.defaults(root, template) if template else {}
        payload: Dict[str, Any] = {}
        for key, value in {**defaults, **(task_payload or {})}.items():
            if value is not None:
                payload[key] = value
        payload.pop("template", None)
        payload.setdefault("title", entry.get("title"))
        if not _text(payload.get("goal")):
            payload["goal"] = _text(entry.get("description")) or _text(entry.get("title"))
        missing = [field for field in ("stage", "scope_write", "acceptance", "gates")
                   if not payload.get(field)]
        if missing:
            raise PolierError("acceptance needs " + ", ".join(missing)
                              + " (provide them in the accept form or pick a template)")
        task = plan_edit.create_task(root, payload)
        entry["status"] = "accepted"
        entry["task"] = task.get("id")
        entry["decision"] = {"by": by, "note": note, "at": dt_now()}
        _write(root, entry)
    return {"intake": entry, "task": task}


def reject(root, intake_id: str, *, by: str = "owner", note: str = "") -> Dict[str, Any]:
    root = Path(root).resolve()
    base = folder(root)
    with FileLock(base / ".intake.lock"):
        entry = get(root, intake_id)
        if entry.get("status") != "proposed":
            raise PolierError(f"intake {intake_id} is already {entry.get('status')}")
        if not _text(note):
            raise PolierError("a rejection needs a reason")
        entry["status"] = "rejected"
        entry["decision"] = {"by": by, "note": note, "at": dt_now()}
        return _write(root, entry)


def summary(root) -> Dict[str, Any]:
    entries = load_all(root)
    counts = {status: 0 for status in STATUSES}
    for entry in entries:
        status = str(entry.get("status") or "proposed")
        counts[status] = counts.get(status, 0) + 1
    return {"counts": counts, "total": len(entries)}
