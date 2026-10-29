#!/usr/bin/env python3
"""Triage intake proposals from the CLI (2.3).

Usage:
    python3 tools/intake.py list [--status proposed|accepted|rejected] [--json]
    python3 tools/intake.py show IN-001 [--json]
    python3 tools/intake.py add --title "…" [--description "…"] [--kind idea|issue|request|question] [--priority low|medium|high] [--link URL]
    python3 tools/intake.py update IN-001 [--title …] [--description …] [--kind …] [--priority …]
    python3 tools/intake.py accept IN-001 --stage <id> [--template <id>] [--scope-write PATH] [--acceptance A1] [--gates GATE] [--estimate-hours 4] [--labels bug] [--note "…"]
    python3 tools/intake.py reject IN-001 --note "reason"

Accepting creates a pending board task through core/plan_edit (validated, schema
auto-upgrade) and links it back to the proposal. The logic lives in
core/intake.py. Exit 0 ok, 1 refused/unknown, 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import intake  # noqa: E402
from core.errors import PolierError  # noqa: E402


def _print(value) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _subparsers(parser):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    return {}


def _add_root_options(sub) -> None:
    for child in sub.choices.values():
        child.add_argument("--root", default=argparse.SUPPRESS)


def _payload(args) -> dict:
    payload = {}
    for field in ("title", "description", "kind", "priority"):
        value = getattr(args, field, None)
        if value is not None:
            payload[field] = value
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="project folder (default: .)")
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", help="list proposals")
    listing.add_argument("--status", choices=intake.STATUSES)
    listing.add_argument("--json", action="store_true")
    show = sub.add_parser("show", help="one proposal")
    show.add_argument("id")
    show.add_argument("--json", action="store_true")
    add = sub.add_parser("add", help="create a proposal")
    add.add_argument("--title", required=True)
    add.add_argument("--description", default="")
    add.add_argument("--kind", choices=intake.KINDS, default="idea")
    add.add_argument("--priority", choices=intake.PRIORITIES, default="medium")
    add.add_argument("--source", choices=intake.SOURCES, default="cli")
    add.add_argument("--link", action="append", default=[])
    update = sub.add_parser("update", help="edit a proposed entry")
    update.add_argument("id")
    update.add_argument("--title")
    update.add_argument("--description")
    update.add_argument("--kind", choices=intake.KINDS)
    update.add_argument("--priority", choices=intake.PRIORITIES)
    accept = sub.add_parser("accept", help="accept and create the task")
    accept.add_argument("id")
    accept.add_argument("--stage", required=True)
    accept.add_argument("--template")
    accept.add_argument("--scope-write", action="append", default=[])
    accept.add_argument("--scope-read", action="append", default=[])
    accept.add_argument("--acceptance", action="append", default=[])
    accept.add_argument("--gates", action="append", default=[])
    accept.add_argument("--depends-on", action="append", default=[])
    accept.add_argument("--labels", action="append", default=[])
    accept.add_argument("--estimate-hours", type=float)
    accept.add_argument("--task-id")
    accept.add_argument("--package")
    accept.add_argument("--complexity", type=int)
    accept.add_argument("--owner")
    accept.add_argument("--note", default="")
    accept.add_argument("--by", default="owner")
    reject = sub.add_parser("reject", help="reject with a reason")
    reject.add_argument("id")
    reject.add_argument("--note", required=True)
    reject.add_argument("--by", default="owner")
    _add_root_options(sub)
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        if args.command == "list":
            entries = intake.load_all(root, getattr(args, "status", None))
            _print({"entries": entries, **intake.summary(root)}) if args.json else [
                print(f"{entry['id']}  {entry['status']:9s}  {entry['priority']:6s}  {entry['title']}")
                for entry in entries]
        elif args.command == "show":
            _print(intake.get(root, args.id))
        elif args.command == "add":
            _print(intake.create(root, {"title": args.title, "description": args.description,
                                        "kind": args.kind, "priority": args.priority,
                                        "links": args.link}, by="cli", source=args.source))
        elif args.command == "update":
            _print(intake.update(root, args.id, _payload(args)))
        elif args.command == "accept":
            task_payload = {}
            for field in ("task_id", "package", "complexity", "estimate_hours", "owner", "template"):
                value = getattr(args, field, None)
                if value is not None:
                    task_payload["id" if field == "task_id" else field] = value
            for field, values in (("scope_write", args.scope_write), ("scope_read", args.scope_read),
                                  ("acceptance", args.acceptance), ("gates", args.gates),
                                  ("depends_on", args.depends_on), ("labels", args.labels)):
                if values:
                    task_payload[field] = values
            task_payload["stage"] = args.stage
            template = task_payload.pop("template", None)
            _print(intake.accept(root, args.id, by=args.by, note=args.note,
                                 task_payload=task_payload, template=template))
        elif args.command == "reject":
            _print(intake.reject(root, args.id, by=args.by, note=args.note))
    except KeyError:
        print("intake.py: unknown intake entry", file=sys.stderr)
        return 1
    except PolierError as exc:
        print(f"intake.py: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
