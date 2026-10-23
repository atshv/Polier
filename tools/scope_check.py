#!/usr/bin/env python3
"""Compare the files changed in a project with the write scope of the running task.

Usage:
    python3 tools/scope_check.py [project] [--task M03] [--allow-board] [--json]

Changed files are everything `git status` reports: modified, staged, untracked,
deleted and both sides of a rename. Ignored files are not counted.

Exit 0 = every change is inside the task's scope, 1 = at least one violation,
2 = usage or environment error (no git repo, invalid board, no unique task).
No external dependencies.
"""
from __future__ import annotations

import argparse
import json
import posixpath
import subprocess
import sys
from pathlib import Path

# Always writable: gate logs and records belong to the task that produced them.
ALWAYS_ALLOWED = ("reviews/evidence",)
# Lead-owned files: a worker must not edit the board, the generated status or briefs.
BOARD_FILES = ("board.json", "STATUS.md", "tasks")


class ScopeError(Exception):
    """Usage or environment problem (exit 2)."""


def normalized(path: str) -> str:
    """Forward slashes, no trailing slash, `.` and `..` resolved."""
    path = path.strip().replace("\\", "/")
    if not path:
        return ""
    clean = posixpath.normpath(path)
    return "" if clean == "." else clean.rstrip("/")


def inside(path: str, entry: str) -> bool:
    """True if `path` equals `entry` or lies below the folder `entry`."""
    path, entry = normalized(path), normalized(entry)
    if not entry:
        return False
    return path == entry or path.startswith(entry + "/")


def changed_files(root: Path) -> list[str]:
    """All changed paths relative to the repository root, in git's order."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1", "-z", "-uall"],
            capture_output=True, check=False,
        )
    except FileNotFoundError as exc:
        raise ScopeError("git not found") from exc
    if result.returncode != 0:
        raise ScopeError(f"not a git repository: {root}")

    prefix = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-prefix"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()

    fields = result.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    paths: list[str] = []
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        paths.append(path)
        if "R" in status or "C" in status:  # rename/copy: the old path follows
            if i < len(fields) and fields[i]:
                paths.append(fields[i])
            i += 1

    # git reports paths relative to the repository root; make them relative to the project.
    out: list[str] = []
    for path in paths:
        rel = normalized(path)
        if prefix:
            pre = normalized(prefix)
            rel = rel[len(pre) + 1:] if rel.startswith(pre + "/") else "../" + rel
        if rel not in out:
            out.append(rel)
    return out


def load_board(root: Path) -> dict:
    path = root / "board.json"
    try:
        board = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ScopeError(f"board.json not found in {root}") from exc
    except ValueError as exc:
        raise ScopeError(f"board.json is invalid: {exc}") from exc
    if not isinstance(board, dict) or not isinstance(board.get("tasks"), list):
        raise ScopeError("board.json has no task list")
    return board


def pick_task(board: dict, task_id: str | None) -> dict:
    tasks = [t for t in board["tasks"] if isinstance(t, dict)]
    if task_id:
        for task in tasks:
            if task.get("id") == task_id:
                return task
        raise ScopeError(f"task {task_id} is not on the board")
    running = [t for t in tasks if t.get("status") == "in_progress"]
    if len(running) == 1:
        return running[0]
    if not running:
        raise ScopeError("no task is in_progress; pass --task <ID>")
    ids = ", ".join(str(t.get("id")) for t in running)
    raise ScopeError(f"several tasks are in_progress ({ids}); pass --task <ID>")


def violations(paths: list[str], task: dict, allow_board: bool) -> list[tuple[str, str]]:
    allowed = [p for p in task.get("scope_write", []) if isinstance(p, str)]
    forbidden = [p for p in task.get("scope_write_forbidden", []) if isinstance(p, str)]
    found: list[tuple[str, str]] = []
    for path in paths:
        if path.startswith("../") or path == "..":
            found.append((path, "outside the project"))
        elif any(inside(path, f) for f in forbidden):
            found.append((path, "forbidden"))
        elif any(inside(path, a) for a in ALWAYS_ALLOWED):
            continue
        elif any(inside(path, b) for b in BOARD_FILES):
            if not allow_board:
                found.append((path, "lead-owned (board, status or brief)"))
        elif not any(inside(path, a) for a in allowed):
            found.append((path, "outside scope"))
    return found


def check(root: Path, task_id: str | None = None, allow_board: bool = False) -> dict:
    """Run the check and return a result dict; raises ScopeError on exit-2 problems."""
    board = load_board(root)
    task = pick_task(board, task_id)
    paths = changed_files(root)
    found = violations(paths, task, allow_board)
    return {
        "task": task.get("id"),
        "ok": not found,
        "changed": paths,
        "violations": [{"path": p, "reason": r} for p, r in found],
        "scope_write": task.get("scope_write", []),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("project", nargs="?", default=".", help="project folder with board.json")
    parser.add_argument("--task", help="task ID; default: the one task in_progress")
    parser.add_argument("--allow-board", action="store_true",
                        help="allow changes to board.json, STATUS.md and tasks/ (lead)")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args(argv)

    root = Path(args.project).resolve()
    try:
        result = check(root, args.task, args.allow_board)
    except ScopeError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}))
        else:
            print(f"SCOPE ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result))
    elif result["ok"]:
        suffix = "" if result["changed"] else " (no changes)"
        print(f"SCOPE OK {result['task']}{suffix}")
    else:
        print(f"SCOPE FAIL {result['task']}")
        for item in result["violations"]:
            print(f"- {item['path']}: {item['reason']}")
        print(f"allowed: {', '.join(result['scope_write']) or 'nothing'}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
