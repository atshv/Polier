#!/usr/bin/env python3
"""Task templates from the CLI (2.3).

Usage:
    python3 tools/templates.py list [--json]
    python3 tools/templates.py show <id> [--json]
    python3 tools/templates.py save --json <file>|-            # full template
    python3 tools/templates.py save --from-task <ID> --id <id> [--name "…"]
    python3 tools/templates.py delete <id>

Templates live in ``templates/tasks/<id>.json`` and carry the reusable shape of
a task (scope, acceptance, gates, complexity, labels, estimate). The plan
editor, the intake accept form and the API use them as defaults; validation
still runs through core/plan_edit when the task is created.

Exit 0 ok, 1 refused/unknown, 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import task_templates  # noqa: E402
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="project folder (default: .)")
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", help="list templates")
    listing.add_argument("--json", action="store_true")
    show = sub.add_parser("show", help="one template")
    show.add_argument("id")
    show.add_argument("--json", action="store_true")
    save = sub.add_parser("save", help="write a template")
    save.add_argument("--json", help="JSON file, or - for stdin")
    save.add_argument("--from-task", dest="from_task")
    save.add_argument("--id")
    save.add_argument("--name")
    delete = sub.add_parser("delete", help="delete a template")
    delete.add_argument("id")
    _add_root_options(sub)
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        if args.command == "list":
            values = task_templates.load_all(root)
            _print({"templates": values}) if args.json else [
                print(f"{template['id']}  {template.get('name')}") for template in values]
        elif args.command == "show":
            _print(task_templates.get(root, args.id))
        elif args.command == "save":
            if args.from_task:
                if not args.id:
                    parser.error("--id is required together with --from-task")
                _print(task_templates.from_task(root, args.from_task, args.id, name=args.name))
            else:
                if not args.json:
                    parser.error("save needs --json or --from-task")
                text = sys.stdin.read() if args.json == "-" else Path(args.json).read_text(encoding="utf-8")
                payload = json.loads(text)
                if not isinstance(payload, dict):
                    raise PolierError("a template must be a JSON object")
                _print(task_templates.save(root, payload))
        elif args.command == "delete":
            _print(task_templates.delete(root, args.id))
    except KeyError:
        print("templates.py: unknown template/task", file=sys.stderr)
        return 1
    except PolierError as exc:
        print(f"templates.py: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"templates.py: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
