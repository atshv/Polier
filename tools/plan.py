#!/usr/bin/env python3
"""Edit the plan from the CLI: tasks, labels, estimates and stage decisions (2.1).

Usage:
    python3 tools/plan.py create --title "…" --goal "…" --stage foundation \
        --scope-write docs/ --acceptance A1 --gates board-check \
        [--id T-01] [--labels bug,risk-low] [--estimate-hours 4]
    python3 tools/plan.py update T-01 --title "…" --labels bug --estimate-hours 6
    python3 tools/plan.py delete T-01
    python3 tools/plan.py stage foundation decision --decision continue
    python3 tools/plan.py stage foundation move --delta 1
    python3 tools/plan.py suggest-id --prefix T
    python3 tools/plan.py create --json payload.json     # full payload as JSON

The logic lives in core/plan_edit.py: the board is written atomically, validated
with core.board.board_errors, dependency cycles are refused, only pending/
blocked/failed tasks can be deleted, and a 0.9/1.0 board is upgraded to 1.1
when a label or an estimate is added. Labels must exist in dashboard.json.

Exit codes: 0 ok, 1 refused/invalid, 2 usage or environment error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import plan_edit  # noqa: E402
from core.errors import PolierError  # noqa: E402


def _payload(args) -> dict:
    payload = {}
    if args.json:
        text = sys.stdin.read() if args.json == "-" else Path(args.json).read_text(encoding="utf-8")
        value = json.loads(text)
        if not isinstance(value, dict):
            raise PolierError("the JSON payload must be an object")
        payload.update(value)
    for field in ("id", "title", "goal", "why", "stage", "package", "complexity",
                  "estimate_hours", "parallel_group", "owner"):
        value = getattr(args, field, None)
        if value is not None:
            payload[field] = value
    for field, source in (("scope_write", args.scope_write), ("scope_read", args.scope_read),
                          ("acceptance", args.acceptance), ("gates", args.gates),
                          ("depends_on", args.depends_on), ("labels", args.labels),
                          ("satisfies", args.satisfies), ("exclusive", args.exclusive)):
        if source:
            payload[field] = source
    return payload


def _print(value) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="project folder (default: .)")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="create a pending task")
    create.add_argument("--json", help="JSON payload file, or - for stdin")
    create.add_argument("--id")
    create.add_argument("--title")
    create.add_argument("--goal")
    create.add_argument("--why")
    create.add_argument("--stage")
    create.add_argument("--package")
    create.add_argument("--complexity", type=int)
    create.add_argument("--estimate-hours", type=float, dest="estimate_hours")
    create.add_argument("--parallel-group", dest="parallel_group")
    create.add_argument("--owner")
    create.add_argument("--scope-write", action="append", default=[])
    create.add_argument("--scope-read", action="append", default=[])
    create.add_argument("--acceptance", action="append", default=[])
    create.add_argument("--gates", action="append", default=[])
    create.add_argument("--depends-on", action="append", default=[])
    create.add_argument("--labels", action="append", default=[])
    create.add_argument("--satisfies", action="append", default=[])
    create.add_argument("--exclusive", action="append", default=[])

    for name in ("update", "delete"):
        command = sub.add_parser(name, help=f"{name} a task")
        command.add_argument("task", help="task ID")
        if name == "update":
            command.add_argument("--json", help="JSON payload file, or - for stdin")
            command.add_argument("--title")
            command.add_argument("--goal")
            command.add_argument("--why")
            command.add_argument("--stage")
            command.add_argument("--package")
            command.add_argument("--complexity", type=int)
            command.add_argument("--estimate-hours", type=float, dest="estimate_hours")
            command.add_argument("--parallel-group", dest="parallel_group")
            command.add_argument("--owner")
            command.add_argument("--scope-write", action="append", default=[])
            command.add_argument("--scope-read", action="append", default=[])
            command.add_argument("--acceptance", action="append", default=[])
            command.add_argument("--gates", action="append", default=[])
            command.add_argument("--depends-on", action="append", default=[])
            command.add_argument("--labels", action="append", default=[])
            command.add_argument("--satisfies", action="append", default=[])
            command.add_argument("--exclusive", action="append", default=[])

    stage = sub.add_parser("stage", help="stage decision or order")
    stage.add_argument("stage", help="stage id")
    stage.add_argument("verb", choices=("decision", "move"))
    stage.add_argument("--decision", choices=("pending", "continue", "stop"))
    stage.add_argument("--delta", type=int, default=0)

    suggest = sub.add_parser("suggest-id", help="the next free task ID")
    suggest.add_argument("--prefix")

    _add_root_options(sub)
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        if args.command == "create":
            _print(plan_edit.create_task(root, _payload(args)))
        elif args.command == "update":
            _print(plan_edit.update_task(root, args.task, _payload(args)))
        elif args.command == "delete":
            _print(plan_edit.delete_task(root, args.task))
        elif args.command == "stage":
            if args.verb == "decision":
                if not args.decision:
                    parser.error("--decision is required for a stage decision")
                _print(plan_edit.set_stage_decision(root, args.stage, args.decision))
            else:
                _print(plan_edit.move_stage(root, args.stage, args.delta))
        elif args.command == "suggest-id":
            _print({"id": plan_edit.suggest_id(__import__("core.board", fromlist=["load_board"]).load_board(root), args.prefix)})
    except KeyError as exc:
        print(f"plan.py: unknown reference {exc}", file=sys.stderr)
        return 1
    except PolierError as exc:
        print(f"plan.py: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"plan.py: {exc}", file=sys.stderr)
        return 2
    return 0


def _subparsers(parser):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    return {}


def _add_root_options(sub) -> None:
    """Accept --root after the subcommand too (argparse keeps the top-level value)."""
    for child in sub.choices.values():
        child.add_argument("--root", default=argparse.SUPPRESS)
        for grandchild in _subparsers(child).values():
            grandchild.add_argument("--root", default=argparse.SUPPRESS)


if __name__ == "__main__":
    sys.exit(main())
