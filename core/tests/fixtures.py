"""Throwaway projects for the core tests: a board and, optionally, a git repo."""
from __future__ import annotations

import copy
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


# ---------------------------------------------------------------------------
# 1.1 stores: policy.json, gate records, review files
# ---------------------------------------------------------------------------

def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _deep_update(base: dict, extra: dict) -> dict:
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def write_policy(root: Path, extra: dict = None) -> dict:
    """Write the default policy.json of 1.1, deep-merged with `extra`."""
    from core.policy import DEFAULTS
    data = _deep_update(copy.deepcopy(DEFAULTS), extra or {})
    write_json(root / "policy.json", data)
    return data


def gate_record(root: Path, tid: str = "M01", gate: str = "tests", exit_code: int = 0,
                result: str = "pass", **extra) -> str:
    """Write one reviews/evidence record and return its project-relative path."""
    record = {"task": tid, "gate": gate, "exit_code": exit_code, "result": result}
    record.update(extra)
    rel = f"reviews/evidence/{tid}-{gate}-20260101T000000Z.json"
    write_json(root / rel, record)
    return rel


def review_note(root: Path, tid: str = "M01", verdict: str = "pass", text: str = "") -> Path:
    """Write reviews/<ID>.md with a verdict line."""
    body = f"# Review {tid}\n\nverdict: {verdict}\n"
    if text:
        body += f"\n{text}\n"
    path = root / "reviews" / f"{tid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path
