"""Committed project settings for the dashboard (2.1): ``dashboard.json``.

The file is part of the project (committed, reviewable, versioned like
``policy.json``). It holds what the *project* decides, never machine-local
settings:

- ``features``: which optional dashboard views exist (future views default off),
- ``labels``: the label definitions tasks may reference (board schema 1.1),
- ``defaults``: small project defaults (``me`` = the owner handle used by
  "Your Work").

Machine-local things (session provider, gate commands, theme, read state) stay
in ``<git-common-dir>/polier/dashboard/config.json``.

Label palette names map to the dashboard's CSS theme; the file never stores raw
colours, so a theme change updates every label at once.
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

FILE = "dashboard.json"
VERSION = 1
PALETTE = ("neutral", "blue", "green", "amber", "orange", "red", "violet", "teal")
GROUPS = ("type", "risk", "origin", "area", "theme", "custom")
LABEL_ID = re.compile(r"^[a-z][a-z0-9-]{0,40}$")

# Feature flags. Current views are on; planned views default off until built.
FEATURES: Dict[str, bool] = {
    "inbox": True,
    "worklog": True,
    "views": True,
    "labels": True,
    "timeline": True,
    "cycles": True,
    "modules": True,
    "coverage": True,
    "analytics": True,
    "pages": True,
    "intake": True,
    "assistant": True,
    "agents": True,
    "skills": True,
    "mcp": True,
    "automations": True,
    "github": True,
    "setup": True,
}

DEFAULT_LABELS: List[Dict[str, str]] = [
    {"id": "feature", "title": "Feature", "color": "green", "group": "type"},
    {"id": "bug", "title": "Bug", "color": "red", "group": "type"},
    {"id": "chore", "title": "Chore", "color": "neutral", "group": "type"},
    {"id": "experiment", "title": "Experiment", "color": "violet", "group": "type"},
    {"id": "risk-low", "title": "Risk: low", "color": "green", "group": "risk"},
    {"id": "risk-medium", "title": "Risk: medium", "color": "amber", "group": "risk"},
    {"id": "risk-high", "title": "Risk: high", "color": "red", "group": "risk"},
    {"id": "origin-owner", "title": "From owner", "color": "blue", "group": "origin"},
    {"id": "origin-agent", "title": "From agent", "color": "teal", "group": "origin"},
]

DEFAULT_SETTINGS: Dict[str, Any] = {
    "version": VERSION,
    "features": dict(FEATURES),
    "labels": [dict(label) for label in DEFAULT_LABELS],
    "defaults": {"me": "owner", "hours_per_day": 4},
}

LABEL_FIELDS = frozenset({"id", "title", "color", "group"})
TOP_FIELDS = frozenset({"version", "features", "labels", "defaults"})
DEFAULT_FIELDS = frozenset({"me", "hours_per_day"})


def path(root) -> Path:
    return Path(root) / FILE


def defaults() -> Dict[str, Any]:
    return json.loads(json.dumps(DEFAULT_SETTINGS))


def errors(settings: Dict[str, Any]) -> List[str]:
    """Validation errors of a parsed dashboard.json; [] when valid."""
    if not isinstance(settings, dict):
        return ["dashboard.json: the settings must be a JSON object"]
    found: List[str] = []
    for field in sorted(set(settings) - TOP_FIELDS):
        found.append(f"dashboard.json: unknown field {field!r}")
    if settings.get("version") != VERSION:
        found.append(f"dashboard.json: version must be {VERSION} (is {settings.get('version')!r})")

    features = settings.get("features", {})
    if not isinstance(features, dict):
        found.append("dashboard.json: features must be an object")
    else:
        for key, value in features.items():
            if key not in FEATURES:
                found.append(f"dashboard.json: unknown feature {key!r}")
            elif not isinstance(value, bool):
                found.append(f"dashboard.json: feature {key!r} must be true or false")

    labels = settings.get("labels", [])
    if not isinstance(labels, list):
        found.append("dashboard.json: labels must be an array")
        labels = []
    seen = set()
    for index, label in enumerate(labels):
        if not isinstance(label, dict):
            found.append(f"dashboard.json: label {index + 1} must be an object")
            continue
        for field in sorted(set(label) - LABEL_FIELDS):
            found.append(f"dashboard.json: label {index + 1}: unknown field {field!r}")
        label_id = label.get("id")
        if not isinstance(label_id, str) or not LABEL_ID.match(label_id):
            found.append(f"dashboard.json: label {index + 1}: id must be lowercase (a-z, 0-9, '-')")
        elif label_id in seen:
            found.append(f"dashboard.json: duplicate label id {label_id!r}")
        else:
            seen.add(label_id)
        title = label.get("title")
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 60:
            found.append(f"dashboard.json: label {index + 1}: title must be 1–60 characters")
        if label.get("color") not in PALETTE:
            found.append(f"dashboard.json: label {index + 1}: color must be one of {', '.join(PALETTE)}")
        if label.get("group") not in GROUPS:
            found.append(f"dashboard.json: label {index + 1}: group must be one of {', '.join(GROUPS)}")

    defaults_block = settings.get("defaults", {})
    if not isinstance(defaults_block, dict):
        found.append("dashboard.json: defaults must be an object")
    else:
        for field in sorted(set(defaults_block) - DEFAULT_FIELDS):
            found.append(f"dashboard.json: defaults: unknown field {field!r}")
        me = defaults_block.get("me")
        if me is not None and (not isinstance(me, str) or not me.strip()):
            found.append("dashboard.json: defaults.me must be a non-empty string")
        hours = defaults_block.get("hours_per_day")
        if hours is not None and (isinstance(hours, bool) or not isinstance(hours, (int, float))
                                  or not 1 <= hours <= 24):
            found.append("dashboard.json: defaults.hours_per_day must be a number between 1 and 24")
    return found


def load(root, strict: bool = False) -> Dict[str, Any]:
    """The project settings; defaults when the file does not exist yet."""
    root = Path(root)
    settings = defaults()
    target = path(root)
    if not target.is_file():
        return settings
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        if strict:
            raise PolierError(f"cannot read {FILE}: {exc}") from exc
        return settings
    if not isinstance(raw, dict):
        if strict:
            raise PolierError(f"{FILE} must be a JSON object")
        return settings
    merged = defaults()
    merged.update(raw)
    problems = errors(merged)
    if problems and strict:
        raise PolierError("; ".join(problems))
    return merged


def _save_unlocked(root: Path, settings: Dict[str, Any]) -> Dict[str, Any]:
    merged = defaults()
    merged.update({key: value for key, value in settings.items() if value is not None})
    problems = errors(merged)
    if problems:
        raise PolierError("; ".join(problems))
    target = path(root)
    temporary = target.with_name(f"{target.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temporary.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, target)
    return merged


def save(root, settings: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and write dashboard.json atomically."""
    root = Path(root).resolve()
    with FileLock(root / (FILE + ".lock")):
        return _save_unlocked(root, settings)


def features(settings: Dict[str, Any]) -> Dict[str, bool]:
    merged = dict(FEATURES)
    merged.update({key: value for key, value in (settings.get("features") or {}).items()
                   if key in FEATURES and isinstance(value, bool)})
    return merged


def enabled(settings: Dict[str, Any], feature: str) -> bool:
    return bool(features(settings).get(feature, False))


def label_list(settings: Dict[str, Any]) -> List[Dict[str, str]]:
    return [dict(label) for label in settings.get("labels") or [] if isinstance(label, dict)]


def label_map(settings: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    return {str(label.get("id")): label for label in label_list(settings)}


def hours_per_day(settings: Dict[str, Any]) -> float:
    value = (settings.get("defaults") or {}).get("hours_per_day", 4)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 1 <= value <= 24:
        return 4.0
    return float(value)


def me(settings: Dict[str, Any]) -> str:
    value = (settings.get("defaults") or {}).get("me")
    return value.strip() if isinstance(value, str) and value.strip() else "owner"


def _label(position: int, payload: Dict[str, Any]) -> Dict[str, str]:
    if not isinstance(payload, dict):
        raise PolierError("a label must be an object")
    return {
        "id": str(payload.get("id") or ""),
        "title": str(payload.get("title") or "").strip(),
        "color": str(payload.get("color") or "neutral"),
        "group": str(payload.get("group") or "custom"),
    }


def add_label(root, payload: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(root).resolve()
    with FileLock(root / (FILE + ".lock")):
        settings = load(root, strict=True)
        label = _label(len(settings.get("labels") or []), payload)
        labels = label_list(settings)
        if any(existing["id"] == label["id"] for existing in labels):
            raise PolierError(f"label {label['id']!r} already exists")
        labels.append(label)
        settings["labels"] = labels
        settings = _save_unlocked(root, settings)
    return {"label": label, "settings": settings}


def update_label(root, label_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(root).resolve()
    with FileLock(root / (FILE + ".lock")):
        settings = load(root, strict=True)
        labels = label_list(settings)
        index = next((position for position, label in enumerate(labels) if label["id"] == label_id), None)
        if index is None:
            raise KeyError(label_id)
        updated = _label(index, {**labels[index], **payload, "id": label_id})
        labels[index] = updated
        settings["labels"] = labels
        settings = _save_unlocked(root, settings)
    return {"label": updated, "settings": settings}


def delete_label(root, label_id: str, force: bool = False) -> Dict[str, Any]:
    root = Path(root).resolve()
    with FileLock(root / (FILE + ".lock")):
        settings = load(root, strict=True)
        labels = label_list(settings)
        if not any(label["id"] == label_id for label in labels):
            raise KeyError(label_id)
        board = board_mod.load_board(root, strict=False)
        used_by = []
        if board is not None:
            for task in board.get("tasks") or []:
                if isinstance(task, dict) and label_id in (task.get("labels") or []):
                    used_by.append(str(task.get("id")))
        if used_by and not force:
            raise PolierError("label is used by: " + ", ".join(used_by)
                              + " (pass force to remove it from those tasks)")
        if used_by:
            for task in board.get("tasks") or []:
                if isinstance(task, dict) and label_id in (task.get("labels") or []):
                    task["labels"] = [entry for entry in task["labels"] if entry != label_id]
            _write_board(root, board)
        settings["labels"] = [label for label in labels if label["id"] != label_id]
        settings = _save_unlocked(root, settings)
    return {"deleted": label_id, "tasks_updated": used_by, "settings": settings}


def _write_board(root: Path, board: dict) -> None:
    target = root / "board.json"
    temporary = target.with_name(f"{target.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temporary.write_text(json.dumps(board, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, target)
