#!/usr/bin/env python3
"""Run one gate command, keep the full output in a log file, print only a short result.

Usage:
    python3 tools/gate.py --task M03 --name tests -- pytest -q
    python3 tools/gate.py --task M03 --name lint --root /path/to/project -- ruff check .
    python3 tools/gate.py --task M03 --name smoke --shell "bm add x && bm list"
    python3 tools/gate.py --task M03 --name e2e --exclusive e2e -- playwright test

The full output goes to <root>/reviews/evidence/<task>-<name>.log. On success
only one line is printed. On failure the last lines and the lines that look like
errors are printed too. `--exclusive RES` (repeatable) locks a shared resource
for the duration of the run; when board.json exists, the `exclusive` list of the
task is locked automatically too. A busy resource prints one BUSY line, writes a
record with `result: busy` and exits 75 (the command did not run). Infrastructure
failures (ECONNREFUSED, EADDRINUSE, project patterns) are recorded as
`result: infra`. Exit code is otherwise the gate's own exit code (124 on
timeout). No external dependencies. The logic lives in core/gate.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import runs  # noqa: E402
from core.board import load_board, resources  # noqa: E402
from core.errors import PolierError  # noqa: E402
from core.gate import run_gate, summary, valid_name  # noqa: E402


def _from_board(root: Path, task_id: str) -> Tuple[List[str], List[str]]:
    """`exclusive` resources of the task and the board's `resources.infra_patterns`."""
    board = load_board(root, strict=False)
    if board is None:
        return [], []
    exclusive: List[str] = []
    for entry in board.get("tasks") or []:
        if isinstance(entry, dict) and entry.get("id") == task_id:
            values = entry.get("exclusive")
            if isinstance(values, list):
                exclusive = [value for value in values if isinstance(value, str)]
            break
    return exclusive, list(resources(board)["infra_patterns"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--task", required=True, help="task ID, e.g. M03")
    parser.add_argument("--name", required=True, help="gate name, e.g. tests")
    parser.add_argument("--root", default=".", help="project folder (default: current folder)")
    parser.add_argument("--tail", type=int, default=15, help="lines of output to show on failure")
    parser.add_argument("--max-errors", type=int, default=15, help="error-looking lines to show on failure")
    parser.add_argument("--timeout", type=int, default=600, help="seconds before the gate is stopped")
    parser.add_argument("--exclusive", action="append", default=[], metavar="RES",
                        help="resource that must not be used by another gate meanwhile (repeatable)")
    parser.add_argument("--lock-wait", type=float, default=1800.0, metavar="SECONDS",
                        help="wait this long for a busy exclusive resource (default: 1800)")
    parser.add_argument("--lock-ttl", type=float, default=3600.0, metavar="SECONDS",
                        help="a lock older than this is stale (default: 3600)")
    parser.add_argument("--slot", type=int, default=None, metavar="N",
                        help="runtime slot of this worktree; written to the record")
    parser.add_argument("--shell", metavar="COMMAND",
                        help="run one command string through the system shell instead of an argument list")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="gate command after --")
    args = parser.parse_args()

    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if args.shell and command:
        parser.error("use either --shell or a command after --, not both")
    if not args.shell and not command:
        parser.error("gate command missing: put it after --")
    if not valid_name(args.task) or not valid_name(args.name):
        parser.error("--task and --name may only contain letters, digits, '.', '_' and '-'")
    if args.slot is not None and args.slot < 0:
        parser.error("--slot must be 0 or a positive integer")
    if args.lock_wait < 0:
        parser.error("--lock-wait must be 0 or positive")
    if args.lock_ttl <= 0:
        parser.error("--lock-ttl must be positive")

    root = Path(args.root)
    exclusive = list(args.exclusive or [])
    infra_patterns: List[str] = []
    if (root / "board.json").is_file():
        from_board, infra_patterns = _from_board(root, args.task)
        for resource in from_board:
            if resource not in exclusive:
                exclusive.append(resource)

    try:
        result = run_gate(args.shell or command, args.task, args.name, args.root,
                          shell=bool(args.shell), timeout=args.timeout, slot=args.slot,
                          exclusive=exclusive, lock_wait=args.lock_wait,
                          lock_ttl=args.lock_ttl, infra_patterns=infra_patterns)
    except PolierError as exc:
        print(f"gate.py: {exc}", file=sys.stderr)
        return 1

    # 1.1 run record: append a gate event after every written record (pass, fail,
    # timeout, infra or busy). A failure here must never change the gate result.
    if runs.enabled(root):
        try:
            record = result["record_path"].relative_to(result["root"]).as_posix()
            runs.record_gate(result["root"], args.task, args.name,
                             result.get("result"), record)
        except Exception:  # noqa: BLE001 - a gate must not fail because of its run record
            pass

    for line in summary(result, tail=args.tail, max_errors=args.max_errors):
        print(line)
    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
