#!/usr/bin/env python3
"""Read and edit the committed dashboard settings (2.1): dashboard.json.

Usage:
    python3 tools/settings.py show [--json]
    python3 tools/settings.py init
    python3 tools/settings.py feature timeline on
    python3 tools/settings.py me lead
    python3 tools/settings.py label add bug "Bug" --color red --group type
    python3 tools/settings.py label update bug --title "Bug report"
    python3 tools/settings.py label delete bug [--force]

Feature flags control optional dashboard views. Labels are the ids board schema
1.1 tasks may reference; deleting a label that tasks use is refused unless
--force is given (then it is removed from those tasks). The logic lives in
core/settings.py; writes are atomic and validated.

Exit codes: 0 ok, 1 invalid/refused, 2 usage or environment error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import settings as settings_mod  # noqa: E402
from core.errors import PolierError  # noqa: E402


def _print(value, as_json: bool = True) -> None:
    if as_json:
        print(json.dumps(value, indent=2, ensure_ascii=False))
    else:
        print(value)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="project folder (default: .)")
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("show", help="print the settings")
    show.add_argument("--json", action="store_true")
    sub.add_parser("init", help="write dashboard.json with the defaults")
    feature = sub.add_parser("feature", help="turn a feature flag on or off")
    feature.add_argument("name")
    feature.add_argument("state", choices=("on", "off"))
    me = sub.add_parser("me", help="set the owner handle used by Your Work")
    me.add_argument("name")
    label = sub.add_parser("label", help="add, update or delete a label")
    label_sub = label.add_subparsers(dest="label_command", required=True)
    add = label_sub.add_parser("add")
    add.add_argument("id")
    add.add_argument("title")
    add.add_argument("--color", default="neutral")
    add.add_argument("--group", default="custom")
    update = label_sub.add_parser("update")
    update.add_argument("id")
    update.add_argument("--title")
    update.add_argument("--color")
    update.add_argument("--group")
    delete = label_sub.add_parser("delete")
    delete.add_argument("id")
    delete.add_argument("--force", action="store_true")
    _add_root_options(sub)
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        if args.command == "show":
            value = settings_mod.load(root)
            if args.json:
                _print(value)
            else:
                print(f"me: {settings_mod.me(value)}")
                for name, on in settings_mod.features(value).items():
                    print(f"feature {name}: {'on' if on else 'off'}")
                for label in settings_mod.label_list(value):
                    print(f"label {label['id']}  {label['title']}  {label['color']}  {label['group']}")
        elif args.command == "init":
            _print(settings_mod.save(root, settings_mod.defaults()))
        elif args.command == "feature":
            value = settings_mod.load(root)
            features = dict(value.get("features") or {})
            features[args.name] = args.state == "on"
            _print(settings_mod.save(root, {**value, "features": features}))
        elif args.command == "me":
            value = settings_mod.load(root)
            _print(settings_mod.save(root, {**value, "defaults": {"me": args.name}}))
        elif args.command == "label":
            if args.label_command == "add":
                _print(settings_mod.add_label(root, {
                    "id": args.id, "title": args.title, "color": args.color, "group": args.group}))
            elif args.label_command == "update":
                payload = {key: getattr(args, key) for key in ("title", "color", "group")
                           if getattr(args, key) is not None}
                _print(settings_mod.update_label(root, args.id, payload))
            else:
                _print(settings_mod.delete_label(root, args.id, force=args.force))
    except KeyError as exc:
        print(f"settings.py: unknown reference {exc}", file=sys.stderr)
        return 1
    except PolierError as exc:
        print(f"settings.py: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"settings.py: {exc}", file=sys.stderr)
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
