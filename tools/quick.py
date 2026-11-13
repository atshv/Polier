#!/usr/bin/env python3
"""Add one quick-track task to the board when the request qualifies (ADR-0004).

Usage:
    python3 tools/quick.py new TITLE --scope PATH [PATH ...] --accept "WHEN …, THEN …"
                           [--accept ...] [--gate NAME ...] [--satisfies D<n> ...]
                           [--role ROLE] [--root DIR] [--json]

Writes a pending task with ``track: quick`` to board.json and its brief to
tasks/<ID>.md. The task then runs through the ordinary state machine, gates
and review. The rule lives in core/quick.py. --accept (repeatable) states the
expected behaviour and is required; --satisfies names definition-of-done items
of docs/quality.md and is required when no task has touched the files.

Exit codes: 0 created, 1 refused (reasons and the proposal path), 2 usage or
environment error (not a project, invalid board).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import quick  # noqa: E402
from core.board import find_root  # noqa: E402
from core.errors import PolierError  # noqa: E402

__all__ = ["main"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quick.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    new = sub.add_parser("new", help="add one quick task")
    new.add_argument("title")
    new.add_argument("--scope", nargs="+", action="extend", default=[], metavar="PATH")
    new.add_argument("--gate", nargs="+", action="extend", default=None, metavar="NAME")
    new.add_argument("--accept", action="append", default=[], metavar="TEXT")
    new.add_argument("--satisfies", nargs="+", action="extend", default=[], metavar="D")
    new.add_argument("--role")
    new.add_argument("--root")
    new.add_argument("--json", action="store_true")
    return parser


def _out(args, payload: dict, text: str) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else text)


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    root = Path(args.root) if args.root else find_root(Path.cwd())
    if root is None or not (Path(root) / "board.json").is_file():
        print("quick.py: no board.json found; pass --root DIR", file=sys.stderr)
        return 2
    try:
        made = quick.create(root, args.title, args.scope, args.accept, args.gate,
                            args.role, args.satisfies)
    except quick.Refused as exc:
        reasons = exc.reasons
        _out(args, {"ok": False, "task": None, "reasons": reasons, "next": quick.NEXT},
             "refused:\n" + "\n".join(f"- {r}" for r in reasons) + f"\nnext: {quick.NEXT}")
        return 1
    except PolierError as exc:
        print(f"quick.py: {exc}", file=sys.stderr)
        return 2
    nxt = f"the lead sets {made['task']} in_progress (tools/state.py set {made['task']} in_progress)"
    _out(args, {"ok": True, "task": made["task"], "reasons": [], "next": nxt},
         f"created {made['task']} ({made['brief']}), gates: {', '.join(made['gates'])}\nnext: {nxt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
