#!/usr/bin/env python3
"""The dispatch plan: what can run now, in parallel, and what cannot.

Usage:
    python3 tools/dispatch.py [--root DIR] [--json] [--limit N]

Text form: the limits, the running tasks with their attempt count, ``Next wave``,
the later waves, the blocked tasks with the command that unblocks them, the
scope conflicts and the pending approvals. `--json` prints the result of
``core.dispatch.plan`` unchanged; `--limit N` caps the tasks per wave (on top of
``max_in_progress``). Read-only: nothing is written.

Exit codes: 0 ok, 2 usage or environment error (no board, bad limit). The logic
lives in core/dispatch.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.dispatch import plan  # noqa: E402
from core.errors import PolierError  # noqa: E402

__all__ = ["main"]


def _json(value) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _running_line(entry: dict) -> str:
    attempt = entry.get("attempt", 0)
    maximum = entry.get("max_attempts")
    claim = entry.get("claim")
    where = ""
    if isinstance(claim, dict):
        where = f" · claim {claim.get('harness') or '?'}/{claim.get('session') or '?'}"
    return (f"  {entry.get('id')} {entry.get('title') or ''} — {entry.get('status')} · "
            f"attempt {attempt}{'/' + str(maximum) if maximum else ''}{where}").rstrip()


def _wave_line(index: int, wave: list) -> str:
    names = ", ".join(str(entry.get("id")) for entry in wave)
    return f"  Wave {index}: {names}"


def _text(plan: dict) -> None:
    limits = plan.get("limits") or {}
    print(f"DISPATCH {plan.get('project')} (profile {plan.get('profile')})")
    print(f"Limits: max_attempts_per_task {limits.get('max_attempts_per_task')} · "
          f"max_in_progress {limits.get('max_in_progress')}")
    print("")

    print("Running:")
    running = plan.get("running") or []
    if running:
        for entry in running:
            print(_running_line(entry))
    else:
        print("  none")
    print("")

    waves = plan.get("waves") or []
    print("Next wave:")
    if waves:
        for entry in waves[0]:
            print(f"  {entry.get('id')} {entry.get('title') or ''} "
                  f"(brief {entry.get('brief')})".rstrip())
    else:
        print("  none — nothing is ready")
    print("")

    print("Later waves:")
    if len(waves) > 1:
        for index, wave in enumerate(waves[1:], 2):
            print(_wave_line(index, wave))
    else:
        print("  none")
    print("")

    print("Blocked:")
    blocked = plan.get("blocked") or []
    if blocked:
        for entry in blocked:
            print(f"  {entry.get('id')}: {entry.get('reason')}")
            print(f"    action: {entry.get('action')}")
    else:
        print("  none")
    print("")

    print("Conflicts:")
    conflicts = plan.get("conflicts") or []
    if conflicts:
        for conflict in conflicts:
            paths = ", ".join(str(path) for path in conflict.get("paths") or [])
            print(f"  {conflict.get('a')} / {conflict.get('b')}: {paths}")
    else:
        print("  none")
    print("")

    print("Pending approvals:")
    pending = plan.get("approvals_pending") or []
    if pending:
        for record in pending:
            target = f" for {record.get('task')}" if record.get("task") else ""
            print(f"  {record.get('id')} {record.get('action')}{target}")
    else:
        print("  none")
    print("")

    nxt = plan.get("next") or []
    print(f"Next: {', '.join(str(task) for task in nxt) if nxt else 'none'}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--root", default=".",
                        help="project folder holding board.json (default: .)")
    parser.add_argument("--json", action="store_true",
                        help="print core.dispatch.plan() as JSON")
    parser.add_argument("--limit", type=int, metavar="N",
                        help="maximum number of tasks per wave")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be a positive integer")

    try:
        result = plan(Path(args.root), limit=args.limit)
    except PolierError as exc:
        print(f"dispatch.py: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"dispatch.py: {exc}", file=sys.stderr)
        return 2

    if args.json:
        _json(result)
    else:
        _text(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
