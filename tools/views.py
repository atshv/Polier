#!/usr/bin/env python3
"""Saved views from the CLI (2.1): list, show, save and delete views.

Usage:
    python3 tools/views.py list [--json]
    python3 tools/views.py builtin [--json]
    python3 tools/views.py show review-queue
    python3 tools/views.py save views/review-queue.json     # a full view object
    python3 tools/views.py save - < view.json               # from stdin
    python3 tools/views.py delete review-queue

Views live in ``views/<id>.json`` (committed). Built-in views are generated from
core/filters.py and are not files. The logic lives in core/views.py and
core/filters.py; writes are validated and atomic.

Exit codes: 0 ok, 1 refused/invalid, 2 usage or environment error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import filters, settings as settings_mod, views as views_mod  # noqa: E402
from core.errors import PolierError  # noqa: E402


def _print(value) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="project folder (default: .)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("list", "builtin"):
        command = sub.add_parser(name)
        command.add_argument("--json", action="store_true")
    show = sub.add_parser("show")
    show.add_argument("view")
    save = sub.add_parser("save")
    save.add_argument("file", help="a JSON file with the view, or - for stdin")
    delete = sub.add_parser("delete")
    delete.add_argument("view")
    _add_root_options(sub)
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        if args.command == "builtin":
            me = settings_mod.me(settings_mod.load(root))
            _print(filters.builtin_views(me) if args.json else
                   [f"{view['id']}  {view['name']}" for view in filters.builtin_views(me)])
        elif args.command == "list":
            values = views_mod.all_views(root, settings_mod.me(settings_mod.load(root)))
            _print(values if args.json else [f"{view['id']}  {view['name']}" for view in values])
        elif args.command == "show":
            values = views_mod.all_views(root, settings_mod.me(settings_mod.load(root)))
            match = next((view for view in values if view.get("id") == args.view), None)
            if match is None:
                print(f"views.py: unknown view {args.view}", file=sys.stderr)
                return 1
            _print(match)
        elif args.command == "save":
            text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise PolierError("a view must be a JSON object")
            _print(views_mod.save(root, payload))
        elif args.command == "delete":
            _print(views_mod.delete(root, args.view))
    except KeyError as exc:
        print(f"views.py: unknown view {exc}", file=sys.stderr)
        return 1
    except PolierError as exc:
        print(f"views.py: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"views.py: {exc}", file=sys.stderr)
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
