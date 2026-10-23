"""Shared fixtures: a throwaway project with a git repo and a board."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent
TOOLS = PACKAGE / "tools"
sys.path.insert(0, str(TOOLS))


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def task(tid: str = "M01", status: str = "in_progress", **extra) -> dict:
    data = {
        "id": tid, "title": f"Task {tid}", "goal": "Do it.", "status": status,
        "depends_on": [], "complexity": 2, "stage": 1,
        "scope_write": ["src/app.py", "tests/"], "acceptance": ["A1"], "gates": ["tests"],
    }
    data.update(extra)
    return data


def make_project(tasks: list[dict], commit: bool = True) -> Path:
    root = Path(tempfile.mkdtemp(prefix="pl-test-"))
    (root / "board.json").write_text(json.dumps(
        {"project": "t", "profile": "S", "base_branch": "main", "tasks": tasks}, indent=2))
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("x = 1\n")
    (root / "README.md").write_text("readme\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    if commit:
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "chore: scaffold")
    return root


def run_tool(name: str, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOLS / name), *args],
                          capture_output=True, text=True, cwd=cwd, check=False)
