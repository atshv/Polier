"""Throwaway projects for the core tests: a board and, optionally, a git repo."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


def task(tid: str = "M01", status: str = "in_progress", **extra) -> dict:
    data = {
        "id": tid, "title": f"Task {tid}", "goal": "Do it.", "status": status,
        "depends_on": [], "complexity": 2, "stage": 1,
        "scope_write": ["src/app.py", "tests/"], "acceptance": ["A1"], "gates": ["tests"],
    }
    data.update(extra)
    return data


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def project(tasks: list, repo: bool = True) -> Path:
    # Resolved so comparisons stay valid on macOS, where /var is a symlink to /private/var.
    root = Path(tempfile.mkdtemp(prefix="pl-core-")).resolve()
    (root / "board.json").write_text(json.dumps(
        {"project": "t", "profile": "S", "base_branch": "main", "tasks": tasks}, indent=2))
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("x = 1\n")
    (root / "README.md").write_text("readme\n")
    if repo:
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.email", "t@example.com")
        git(root, "config", "user.name", "t")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "chore: scaffold")
    return root


def set_board(root: Path, **changes) -> None:
    board = json.loads((root / "board.json").read_text())
    board.update(changes)
    (root / "board.json").write_text(json.dumps(board))
