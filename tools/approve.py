#!/usr/bin/env python3
"""Human approvals for high-risk actions: request, grant, deny, list, check.

Usage:
    python3 tools/approve.py request --action ACTION [--task ID] [--by worker] [--note TEXT]
    python3 tools/approve.py grant AP-001 [--by owner] [--note TEXT]
    python3 tools/approve.py deny AP-001 [--by owner] [--note TEXT]
    python3 tools/approve.py list [--json] [--status pending|granted|denied]
    python3 tools/approve.py check --action ACTION [--task ID] [--json]
    python3 tools/approve.py --root DIR ...

Records live in reviews/approvals/AP-NNN.json (one file per decision); IDs are
``AP-`` plus three or more digits. A granted record is the approval and does not
expire. An identical pending request is reused instead of creating a second
file. ``check`` exits 0 only when a granted record matches the action and task
(a record without a task matches any task). No external dependencies; the logic
lives in core/approvals.py.

Exit codes: 0 ok, 1 no matching grant / already decided, 2 usage or environment
error (unknown action, malformed ID, invalid task).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import approvals  # noqa: E402
from core.errors import PolierError  # noqa: E402
from core.policy import ACTIONS  # noqa: E402

__all__ = ["main"]


def _json(value) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _describe(record: dict) -> str:
    parts = [str(record.get("id")), str(record.get("status")),
             str(record.get("action"))]
    task = record.get("task")
    if task is not None:
        parts.append(f"task {task}")
    return " · ".join(parts)


def _print_record(record: dict, verb: str) -> None:
    who = record.get("approved_by") or record.get("requested_by") or "?"
    print(f"APPROVAL {_describe(record)} · {verb} by {who}")
    note = record.get("note")
    if note:
        print(f"  note: {note}")


def _request(args) -> int:
    if not isinstance(args.by, str) or not args.by.strip():
        print("approve.py: --by must name who requests", file=sys.stderr)
        return 2
    before = {record.get("id") for record in approvals.load_all(args.root)}
    record = approvals.request(args.root, args.action, task=args.task, by=args.by,
                               note=args.note or "")
    reused = record.get("id") in before
    verb = "reused" if reused else "requested"
    _print_record(record, verb)
    return 0


def _decide(args, status: str) -> int:
    if not isinstance(args.by, str) or not args.by.strip():
        print("approve.py: --by must name who decides", file=sys.stderr)
        return 2
    if not approvals.valid_id(args.approval_id):
        print(f"approve.py: invalid approval id {args.approval_id!r} "
              "(expected AP- plus at least 3 digits)", file=sys.stderr)
        return 2
    try:
        call = approvals.grant if status == "granted" else approvals.deny
        record = call(args.root, args.approval_id, args.by, args.note or "")
    except PolierError as exc:
        print(f"approve.py: {exc}", file=sys.stderr)
        return 1
    _print_record(record, "granted" if status == "granted" else "denied")
    return 0


def _list(args) -> int:
    records = approvals.load_all(args.root)
    if args.status:
        records = [record for record in records if record.get("status") == args.status]
    if args.json:
        _json(records)
        return 0
    if not records:
        print("NO APPROVALS")
        return 0
    for record in records:
        print(_describe(record)
              + (f" · requested by {record.get('requested_by')}"
                 if record.get("requested_by") else "")
              + (f" · note: {record.get('note')}" if record.get("note") else ""))
    return 0


def _check(args) -> int:
    record = approvals.granted(args.root, args.action, task=args.task)
    granted = record is not None
    if args.json:
        _json({"action": args.action, "task": args.task, "granted": granted,
               "approval": record})
        return 0 if granted else 1
    target = f" for {args.task}" if args.task else ""
    if granted:
        print(f"GRANTED {args.action}{target} · {record.get('id')} "
              f"by {record.get('approved_by')}")
        return 0
    print(f"NOT GRANTED {args.action}{target}: no matching granted approval")
    return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--root", default=".",
                        help="project folder holding reviews/approvals (default: .)")
    sub = parser.add_subparsers(dest="command", required=True)

    request_p = sub.add_parser("request", help="request an approval")
    request_p.add_argument("--action", required=True, choices=ACTIONS,
                           help="action that needs an approval")
    request_p.add_argument("--task", help="task the approval concerns (default: none)")
    request_p.add_argument("--by", default="worker", help="who requests it (default: worker)")
    request_p.add_argument("--note", help="why the action is needed")
    request_p.add_argument("--root", dest="root", default=argparse.SUPPRESS,
                           help="project folder (default: .)")

    grant_p = sub.add_parser("grant", help="grant a pending approval")
    grant_p.add_argument("approval_id", help="approval ID, e.g. AP-001")
    grant_p.add_argument("--by", default="owner", help="who grants it (default: owner)")
    grant_p.add_argument("--note", help="note appended to the record")
    grant_p.add_argument("--root", dest="root", default=argparse.SUPPRESS,
                         help="project folder (default: .)")

    deny_p = sub.add_parser("deny", help="deny a pending approval")
    deny_p.add_argument("approval_id", help="approval ID, e.g. AP-001")
    deny_p.add_argument("--by", default="owner", help="who denies it (default: owner)")
    deny_p.add_argument("--note", help="note appended to the record")
    deny_p.add_argument("--root", dest="root", default=argparse.SUPPRESS,
                        help="project folder (default: .)")

    list_p = sub.add_parser("list", help="list the approval records")
    list_p.add_argument("--json", action="store_true", help="print the records as JSON")
    list_p.add_argument("--status", choices=approvals.STATUSES,
                        help="only records with this status")
    list_p.add_argument("--root", dest="root", default=argparse.SUPPRESS,
                        help="project folder (default: .)")

    check_p = sub.add_parser("check", help="exit 0 only when a granted approval matches")
    check_p.add_argument("--action", required=True, choices=ACTIONS,
                         help="action to look up")
    check_p.add_argument("--task", help="task to look up (a record without a task matches)")
    check_p.add_argument("--json", action="store_true", help="print the result as JSON")
    check_p.add_argument("--root", dest="root", default=argparse.SUPPRESS,
                         help="project folder (default: .)")

    args = parser.parse_args(argv)
    args.root = Path(args.root)

    try:
        if args.command == "request":
            return _request(args)
        if args.command == "grant":
            return _decide(args, "granted")
        if args.command == "deny":
            return _decide(args, "denied")
        if args.command == "list":
            return _list(args)
        return _check(args)
    except PolierError as exc:
        print(f"approve.py: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"approve.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
