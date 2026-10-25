#!/usr/bin/env python3
"""Runtime slots: ports, test database names and buckets per worktree (PL-02).

Usage:
    python3 tools/slot.py acquire [--root PATH] [--reclaim-stale] [--json]
    python3 tools/slot.py release [--root PATH] [--json]
    python3 tools/slot.py show    [--root PATH] [--json]
    python3 tools/slot.py list    [--root PATH] [--json]

A slot avoids port and database collisions when several worktrees run servers
and tests at the same time. `acquire` writes `.polier-slot` in the worktree
root and registers it in `<git-common-dir>/polier/slots.json`; slot 0 is the
main checkout and is never registered. `list` marks slots whose worktree folder
is gone as stale; `acquire --reclaim-stale` reuses them. Polier does not create
databases or buckets, it only prints their names - a project's
`tools/dev/setup` reads `.polier-slot`.

Exit codes: 0 ok, 1 error (no free slot, no slot file, not a repository),
2 usage. No external dependencies; the logic lives in core/slots.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.errors import PolierError  # noqa: E402
from core.slots import acquire, list_slots, load_slot, release  # noqa: E402


def describe(data: dict) -> str:
    """One human-readable line: `slot 2: web=4200 api=4201 · db bm_slot_2 · bucket bm-slot-2`."""
    ports = " ".join(f"{name}={port}" for name, port in sorted((data.get("ports") or {}).items()))
    line = f"slot {data.get('slot')}"
    if ports:
        line += f": {ports}"
    line += f" · db {data.get('db_name')} · bucket {data.get('bucket')}"
    return line


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("acquire", "take a slot for this worktree (or reuse its .polier-slot)"),
        ("release", "remove .polier-slot and the registry entry"),
        ("show", "print the slot of this worktree"),
        ("list", "list every registered slot; stale ones have no worktree folder"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--root", default=".",
                             help="worktree or project folder (default: current folder)")
        command.add_argument("--json", action="store_true", help="print one JSON object")
        if name == "acquire":
            command.add_argument("--reclaim-stale", action="store_true",
                                 help="reuse slots whose worktree folder is gone")
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except PolierError as exc:
        print(f"slot.py: {exc}", file=sys.stderr)
        return 1


def _run(args) -> int:
    if args.command == "acquire":
        data = acquire(args.root, reclaim_stale=args.reclaim_stale)
        print(describe(data) if not args.json else json.dumps(data, indent=2))
        return 0

    if args.command == "release":
        data = release(args.root)
        if data is None:
            print(f"slot.py: no .polier-slot in {Path(args.root).resolve()}", file=sys.stderr)
            return 1
        payload = {"released": True, **data}
        print(json.dumps(payload, indent=2) if args.json else f"released slot {data.get('slot')}")
        return 0

    if args.command == "show":
        data = load_slot(args.root)
        if data is None:
            print(f"slot.py: no .polier-slot in {Path(args.root).resolve()} "
                  f"— run: python3 tools/slot.py acquire", file=sys.stderr)
            return 1
        print(json.dumps(data, indent=2) if args.json else describe(data))
        return 0

    slots = list_slots(args.root)
    if args.json:
        print(json.dumps({"slots": slots}, indent=2))
        return 0
    if not slots:
        print("no slots registered")
        return 0
    for entry in slots:
        line = describe(entry)
        if entry.get("stale"):
            line += f" · stale (worktree gone: {entry.get('worktree')})"
        else:
            line += f" · {entry.get('worktree')}"
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
