#!/usr/bin/env python3
"""The compliance view of the board: statuses against runs, gates, reviews and approvals.

Usage:
    python3 tools/audit.py [--root DIR] [--json] [--task ID]

One block per task: board status, attempts used/limit, the gates and their
passing records, the review file and verdict, the handoff, the approvals per
action and the run record; then the errors and warnings of the whole board. For
a ``done`` task an enabled check that fails is an error (exit 1); for every other
status it is a warning. `--json` prints the result of ``core.audit.audit``;
`--task ID` restricts the view to one task (the exit code follows its errors).

Exit codes: 0 no errors, 1 any error, 2 usage or environment error (no board,
unknown task). The logic lives in core/audit.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.audit import audit  # noqa: E402
from core.board import load_board  # noqa: E402
from core.errors import PolierError  # noqa: E402

__all__ = ["main"]


def _json(value) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _yes(value) -> str:
    return "yes" if value else "no"


def _gates(record: dict) -> str:
    gates = record.get("gates") or []
    if not gates:
        return "none listed"
    passed = set(record.get("passed") or [])
    return ", ".join(f"{gate} ({'pass' if gate in passed else 'missing'})" for gate in gates)


def _review(record: dict) -> str:
    review = record.get("review") or {}
    if not review.get("present"):
        return f"{review.get('file', '?')} (missing)"
    return f"{review.get('file')} verdict: {review.get('verdict') or 'none'}"


def _approvals(record: dict) -> str:
    entries = [entry for entry in record.get("approvals") or []
               if entry.get("status") in ("granted", "pending")]
    if not entries:
        return "none"
    return ", ".join(f"{entry.get('action')} {entry.get('status')} ({entry.get('id')})"
                     for entry in entries)


def _block(record: dict) -> list:
    attempt = record.get("attempts", 0)
    maximum = record.get("max_attempts")
    lines = [
        f"{record.get('task')} {record.get('title') or ''}".rstrip(),
        f"  status: {record.get('status')} · attempts: {attempt}"
        f"{'/' + str(maximum) if maximum else ''}",
        f"  gates: {_gates(record)}",
        f"  review: {_review(record)}",
        f"  handoff: {len(record.get('handoff') or [])} line(s)",
        f"  approvals: {_approvals(record)}",
        f"  run record: {_yes(record.get('run_record'))}"
        + (f" · dependency manifest: {record['dependency_manifest']}"
           if record.get("dependency_manifest") else ""),
    ]
    for label, key in (("error", "errors"), ("warning", "warnings")):
        values = record.get(key) or []
        for value in values:
            lines.append(f"  {label}: {value}")
    return lines


def _text(result: dict) -> None:
    for record in result.get("tasks") or []:
        print("\n".join(_block(record)))
        print("")
    errors = result.get("errors") or []
    warnings = result.get("warnings") or []
    if errors:
        print(f"ERRORS ({len(errors)}):")
        for error in errors:
            print(f"  - {error}")
    else:
        print("ERRORS: none")
    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for warning in warnings:
            print(f"  - {warning}")
    else:
        print("WARNINGS: none")
    print(f"audit: {len(errors)} error(s), {len(warnings)} warning(s)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--root", default=".",
                        help="project folder holding board.json (default: .)")
    parser.add_argument("--json", action="store_true",
                        help="print core.audit.audit() as JSON")
    parser.add_argument("--task", help="only this task ID")
    args = parser.parse_args(argv)
    root = Path(args.root)

    try:
        board = load_board(root)
        result = audit(root, board)
        if args.task:
            record = next((item for item in result["tasks"]
                           if item.get("task") == args.task), None)
            if record is None:
                raise PolierError(f"task {args.task} is not on the board")
            result = {"tasks": [record], "errors": list(record.get("errors") or []),
                      "warnings": list(record.get("warnings") or [])}
    except PolierError as exc:
        print(f"audit.py: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"audit.py: {exc}", file=sys.stderr)
        return 2

    if args.json:
        _json(result)
    else:
        _text(result)
    return 1 if result.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
