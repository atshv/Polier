#!/usr/bin/env python3
"""Token use per task: record it and compare it with the budget in policy.json.

Usage:
    python3 tools/usage.py record M03 --tokens 120000 [--session ID] [--source NAME]
    python3 tools/usage.py show [M03] [--json]
    python3 tools/usage.py --root DIR ...

`record` stores the tokens a session spent on a task in ``runs/<ID>.json``.
With ``--session`` the number is that session's running total and replaces its
earlier report; without it the number is added as a separate manual entry. The
Claude Code Stop hook records its session automatically; other harnesses, or a
human reading the cost page of a provider, use this command.

`show` lists every task with recorded tokens (or one task) against
``budget.max_tokens_per_task``. A task at or over the budget is marked
``OVER``; at ``budget.warn_at`` (default 80 %) it is marked ``WARN``. Once the
budget is used, ``tools/state.py`` refuses another ``in_progress`` for the task
until the owner grants a ``state_override``. Without a budget the numbers are
shown for information only.

Exit codes: 0 ok, 1 a task is over its budget, 2 usage or environment error.
No external dependencies; the logic lives in core/runs.py and core/policy.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import runs  # noqa: E402
from core.board import load_board, tasks_of  # noqa: E402
from core.errors import PolierError  # noqa: E402
from core.policy import budget, load_policy  # noqa: E402

__all__ = ["main", "report"]


def report(root: Path, task_id=None) -> dict:
    """Tokens per task against the budget: ``{"max_tokens", "warn_at", "tasks"}``."""
    try:
        policy = load_policy(root)
    except PolierError:
        policy = {"enabled": False}
    plan = budget(policy)
    limit = plan["max_tokens_per_task"]
    board = load_board(root, strict=False) or {}
    ids = [task.get("id") for task in tasks_of(board) if isinstance(task.get("id"), str)]
    if task_id:
        if task_id not in ids:
            raise PolierError(f"task {task_id} is not on the board")
        ids = [task_id]
    rows = []
    for tid in ids:
        record = runs.load_run(root, tid)
        used = sum(entry["tokens"] for entry in record["usage"].values())
        if not used and not task_id:
            continue
        state = "ok"
        if limit and used >= limit:
            state = "over"
        elif limit and used >= limit * plan["warn_at"]:
            state = "warn"
        rows.append({"task": tid, "tokens": used, "sessions": len(record["usage"]), "state": state})
    return {"max_tokens": limit, "warn_at": plan["warn_at"], "tasks": rows}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record", help="store the tokens a session spent on a task")
    rec.add_argument("task")
    rec.add_argument("--tokens", type=int, required=True)
    rec.add_argument("--session", default=None)
    rec.add_argument("--source", default="manual")
    show = sub.add_parser("show", help="tokens per task against the budget")
    show.add_argument("task", nargs="?")
    show.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).expanduser().resolve()

    try:
        if args.command == "record":
            board = load_board(root, strict=False) or {}
            if args.task not in {task.get("id") for task in tasks_of(board)}:
                raise PolierError(f"task {args.task} is not on the board")
            runs.record_usage(root, args.task, args.tokens, session=args.session, source=args.source)
            total = runs.usage_total(root, args.task)
            print(f"USAGE {args.task}: {total:,} tokens recorded")
            data = report(root, args.task)
            row = data["tasks"][0]
            if row["state"] != "ok":
                print(f"{row['state'].upper()}: {total:,} of {data['max_tokens']:,} tokens "
                      f"(budget.max_tokens_per_task)")
            return 1 if row["state"] == "over" else 0

        data = report(root, args.task)
        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
        else:
            cap = f"{data['max_tokens']:,} per task" if data["max_tokens"] else "none"
            print(f"TOKENS · budget: {cap}")
            if not data["tasks"]:
                print("  no usage recorded")
            for row in data["tasks"]:
                mark = {"ok": "", "warn": "  WARN", "over": "  OVER"}[row["state"]]
                share = (f" ({row['tokens'] * 100 // data['max_tokens']} %)"
                         if data["max_tokens"] else "")
                print(f"  {row['task']}: {row['tokens']:,}{share}{mark}")
        return 1 if any(row["state"] == "over" for row in data["tasks"]) else 0
    except PolierError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
