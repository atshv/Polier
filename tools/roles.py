#!/usr/bin/env python3
"""Specialist roles of a project: the package's, adjusted by docs/roles/.

Usage:
    python3 tools/roles.py list [--json] [--root DIR]
    python3 tools/roles.py show ROLE [--json] [--root DIR]
    python3 tools/roles.py check [--root DIR]

The logic lives in core/roles.py. Exit codes: 0 ok, 1 check found problems,
2 usage error or unknown role.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import factory, roles  # noqa: E402
from core.errors import PolierError  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Polier specialist roles.")
    parser.add_argument("--root", default=".", help="project folder (default: .)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("list", "show", "check"):
        p = sub.add_parser(name)
        p.add_argument("--root", dest="root", default=argparse.SUPPRESS)
        if name == "show":
            p.add_argument("role")
        if name != "check":
            p.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        loaded = roles.load(root)
    except PolierError as exc:
        print(f"roles.py: {exc}", file=sys.stderr)
        return 2
    if args.command == "check":
        problems = roles.errors(root, factory.station_ids())
        for problem in problems:
            print(f"error: {problem}")
        if not problems:
            print(f"roles ok · {len(loaded)} roles")
        return 1 if problems else 0
    if args.command == "list":
        rows = [{k: v for k, v in role.items()} for role in loaded.values()]
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        else:
            for role in rows:
                name = f" ({role['name']})" if role.get("name") else ""
                print(f"{role['id']:<18} {role['title']}{name} · {', '.join(role.get('stations') or [])} · {role['mode']}")
        return 0
    role = loaded.get(args.role)
    if role is None:
        print(f"roles.py: unknown role {args.role!r}; known: {', '.join(sorted(loaded))}", file=sys.stderr)
        return 2
    value = {**role, "instructions": roles.instructions(args.role, root)}
    if args.json:
        print(json.dumps(value, indent=2, ensure_ascii=False))
    else:
        print(f"{value['title']} ({value['id']}) · {value['mode']} · model {value['model']}")
        print(value["focus"])
        print()
        print(value["instructions"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
