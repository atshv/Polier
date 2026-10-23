#!/usr/bin/env python3
"""Compare the files changed in a project with the write scope of the running task.

Usage:
    python3 tools/scope_check.py [project] [--task M03] [--allow-board] [--json]

Changed files are everything `git status` reports: modified, staged, untracked,
deleted and both sides of a rename. Ignored files are not counted.

Exit 0 = every change is inside the task's scope, 1 = at least one violation,
2 = usage or environment error (no git repo, invalid board, no unique task).
No external dependencies. The rules live in core/scope.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.board import load_board, pick_task  # noqa: E402
from core.errors import PolierError as ScopeError  # noqa: E402
from core.paths import inside, normalized  # noqa: E402
from core.scope import ALWAYS_ALLOWED, BOARD_FILES, changed_files, violations  # noqa: E402
from core.scope import scope_check as check  # noqa: E402

__all__ = ["ALWAYS_ALLOWED", "BOARD_FILES", "ScopeError", "changed_files", "check", "inside",
           "load_board", "main", "normalized", "pick_task", "violations"]


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
