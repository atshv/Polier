#!/usr/bin/env python3
"""Show and change the state of a task; the only writer of the board status in 1.1.

Usage:
    python3 tools/state.py show [ID] [--json] [--root DIR]
    python3 tools/state.py set ID STATUS [--actor lead] [--note TEXT] [--force] [--root DIR]
    python3 tools/state.py check ID STATUS [--json] [--root DIR]

`show` prints the board status against the run record, attempts, gates, review,
handoff and approvals (the whole board when ID is omitted); `check` evaluates a
transition without writing; `set` applies it, records the side effects (attempt
open/close, round, events) and prints what comes next. A refusal prints every
blocker and the command that unblocks it. `--force` needs a granted
state_override approval.

Exit codes: 0 ok, 1 refused transition / failed check, 2 usage or environment
error (not a board, unknown task for `set`). The logic lives in core/state.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import state  # noqa: E402
from core.board import load_board, tasks_of  # noqa: E402
from core.errors import PolierError  # noqa: E402

__all__ = ["main"]


def _json(value) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _yes(value) -> str:
    return "yes" if value else "no"


def _list(values) -> str:
    return ", ".join(str(value) for value in values) if values else "none"


def _gate_line(status: dict) -> str:
    gates = status.get("gates") or []
    if not gates:
        return "none listed"
    passed = set(status.get("passed") or [])
    return ", ".join(f"{gate} ({'pass' if gate in passed else 'missing'})" for gate in gates)


def _review_line(status: dict) -> str:
    review = status.get("review") or {}
    file = review.get("file") or "?"
    if not review.get("present"):
        return f"{file} (missing)"
    return f"{file} verdict: {review.get('verdict') or 'none'}"


def _show_text(status: dict, title: str = "") -> None:
    attempt = status.get("attempt", 0)
    maximum = status.get("max_attempts")
    limit = f"/{maximum}" if maximum else ""
    print(f"{status.get('task')} {title}".rstrip())
    print(f"  status: {status.get('status')} (board) · run: {status.get('state')}")
    print(f"  attempt: {attempt}{limit} · round: {status.get('round', 0)}"
          + (f" · stage: {status.get('stage')}" if status.get("stage") else ""))
    print(f"  gates: {_gate_line(status)}")
    print(f"  review: {_review_line(status)}")
    print(f"  handoff: {_list([line for line in status.get('handoff') or [] if line])}")
    print(f"  run record: {_yes(status.get('run_record'))}"
          + (f" · dependency manifest: {status.get('dependency_manifest')}"
             if status.get("dependency_manifest") else ""))
    granted = [item.get("id") for item in status.get("approvals_granted") or []
               if item.get("id")]
    pending = [item.get("id") for item in status.get("approvals_pending") or []
               if item.get("id")]
    print(f"  approvals: granted {_list(granted)} · pending {_list(pending)}")
    print(f"  policy: {'on' if status.get('policy') else 'off'}"
          + (f" · warning: {status['policy_warning']}" if status.get("policy_warning") else ""))


def _show_board(root: Path, as_json: bool) -> int:
    board = load_board(root)
    statuses = [state.status_of(root, task.get("id")) for task in tasks_of(board)
                if isinstance(task.get("id"), str)]
    if as_json:
        _json({"project": board.get("project"), "profile": board.get("profile"),
               "tasks": statuses})
        return 0
    print(f"{board.get('project')} (profile {board.get('profile')})")
    for status in statuses:
        attempt = status.get("attempt", 0)
        maximum = status.get("max_attempts")
        missing = status.get("missing_gates") or []
        print(f"  {status.get('task')}  {str(status.get('status')):<12} "
              f"attempt {attempt}{'/' + str(maximum) if maximum else ''}  "
              f"round {status.get('round', 0)}  "
              f"gates missing: {_list(missing)}")
    return 0


def _print_warnings(warnings) -> None:
    for warning in warnings or []:
        print(f"warning: {warning}")


def _print_actions(actions) -> None:
    for action in actions or []:
        command = action.get("command", "")
        reason = action.get("reason", "")
        print(f"  action: {command}")
        if reason:
            print(f"    reason: {reason}")


def _refusal(task: str, status: str, result: dict) -> int:
    print(f"REFUSED {task} → {status}")
    for error in result.get("errors") or []:
        print(f"  blocker: {error}")
    if result.get("actions"):
        print("  unblock:")
        _print_actions(result.get("actions"))
    _print_warnings(result.get("warnings"))
    return 1


def _set_text(result: dict) -> None:
    print(f"{result.get('task')}: {result.get('from')} → {result.get('to')} "
          f"(actor {result.get('actor')})")
    attempt = result.get("attempt", 0)
    maximum = result.get("max_attempts")
    print(f"attempt {attempt}{'/' + str(maximum) if maximum else ''} · "
          f"round {result.get('round', 0)} · run state: {result.get('state')}")
    _print_warnings(result.get("warnings"))
    if result.get("forced"):
        for message in result.get("forced"):
            print(f"forced: {message}")
    if result.get("next"):
        print(f"next: {result.get('next')}")
    else:
        print("next: none — the task is done")


def _check_text(task: str, status: str, result: dict) -> int:
    if result.get("ok"):
        print(f"OK {task} {result.get('from')} → {status}")
        _print_warnings(result.get("warnings"))
        return 0
    return _refusal(task, status, result)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def root_arg(sub_parser) -> None:
        sub_parser.add_argument("--root", default=".",
                                help="project folder holding board.json (default: .)")

    show_p = sub.add_parser("show", help="show the state of one task or of the whole board")
    show_p.add_argument("task", nargs="?", help="task ID; without it the whole board")
    show_p.add_argument("--json", action="store_true", help="print the state as JSON")
    root_arg(show_p)

    set_p = sub.add_parser("set", help="change a task status through its checkpoints")
    set_p.add_argument("task", help="task ID, e.g. M03")
    set_p.add_argument("status", choices=state.STATUSES, help="new status")
    set_p.add_argument("--actor", default="lead", help="who changes the state (default: lead)")
    set_p.add_argument("--note", help="reason; required for rework, blocked and failed")
    set_p.add_argument("--force", action="store_true",
                       help="override a checkpoint; needs a granted state_override approval")
    root_arg(set_p)

    check_p = sub.add_parser("check", help="evaluate a transition without writing anything")
    check_p.add_argument("task", help="task ID, e.g. M03")
    check_p.add_argument("status", choices=state.STATUSES, help="target status")
    check_p.add_argument("--json", action="store_true", help="print the evaluation as JSON")
    root_arg(check_p)

    args = parser.parse_args(argv)
    root = Path(args.root)

    try:
        if args.command == "show":
            if args.task:
                board = load_board(root)
                entry = next((task for task in tasks_of(board)
                              if task.get("id") == args.task), None)
                status = state.status_of(root, args.task)
                if args.json:
                    _json(status)
                else:
                    _show_text(status, str((entry or {}).get("title") or ""))
            else:
                return _show_board(root, args.json)
            return 0

        if args.command == "check":
            board = load_board(root)
            result = state.check_transition(root, board, args.task, args.status)
            if args.json:
                _json(result)
                return 0 if result.get("ok") else 1
            return _check_text(args.task, args.status, result)

        result = state.set_status(root, args.task, args.status, actor=args.actor,
                                  note=args.note, force=args.force)
        _set_text(result)
        return 0
    except state.TransitionBlocked as exc:
        return _refusal(args.task, args.status, exc.result)
    except PolierError as exc:
        print(f"state.py: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"state.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
