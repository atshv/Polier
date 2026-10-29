"""Runtime folder for the dashboard: transcripts, job logs and plan drafts.

Everything the dashboard writes outside the project files lives in git's
administrative folder so it is shared by every worktree of the repository and
never lands in the working tree:

``<git-common-dir>/polier/dashboard/``

Outside a git repository the dashboard falls back to ``<project>/.polier-dashboard``
and says so in the UI. The folder holds no project state: deleting it only
loses transcripts and job logs.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .errors import PolierError

FOLDER = "dashboard"


def runtime_dir(root) -> Path:
    """The dashboard runtime folder for `root`, created on demand."""
    from .paths import git_common_dir

    root = Path(root).resolve()
    try:
        base = git_common_dir(root) / "polier" / FOLDER
    except PolierError:
        base = root / ".polier-dashboard"
    base.mkdir(parents=True, exist_ok=True)
    return base


def sub(self_root, *parts: str) -> Path:
    """A subfolder of the runtime dir (created)."""
    path = runtime_dir(self_root).joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(default or {})
    return value if isinstance(value, dict) else dict(default or {})


def write_json(path: Path, value: Any) -> None:
    """Atomic write with a temporary file next to the target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{int(time.time() * 1000)}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{int(time.time() * 1000)}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line if line.endswith("\n") else line + "\n")
