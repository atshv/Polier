"""Shared fixtures for the dashboard tests: a throwaway schema-1.0 project."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent
EXAMPLES = PACKAGE / "examples" / "monorepo-mini"
sys.path.insert(0, str(PACKAGE))


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def sample_project() -> Path:
    """A copy of the monorepo example in a fresh git repository."""
    root = Path(tempfile.mkdtemp(prefix="pl-dash-"))
    shutil.copytree(EXAMPLES, root, dirs_exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "dash@example.com")
    git(root, "config", "user.name", "dash")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: fixture")
    return root


def empty_project() -> Path:
    """An empty folder with a git repository, ready for the interview wizard."""
    root = Path(tempfile.mkdtemp(prefix="pl-dash-empty-"))
    (root / "README.md").write_text("empty\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "dash@example.com")
    git(root, "config", "user.name", "dash")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: scaffold")
    return root
