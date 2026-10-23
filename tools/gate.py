#!/usr/bin/env python3
"""Run one gate command, keep the full output in a log file, print only a short result.

Usage:
    python3 tools/gate.py --task M03 --name tests -- pytest -q
    python3 tools/gate.py --task M03 --name lint --root /path/to/project -- ruff check .
    python3 tools/gate.py --task M03 --name smoke --shell "bm add x && bm list"

The full output goes to <root>/reviews/evidence/<task>-<name>.log.
On success only one line is printed. On failure the last lines and the lines that
look like errors are printed too. Exit code is the gate's own exit code
(124 on timeout). No external dependencies. The logic lives in core/gate.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.gate import run_gate, summary, valid_name  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--task", required=True, help="task ID, e.g. M03")
    parser.add_argument("--name", required=True, help="gate name, e.g. tests")
    parser.add_argument("--root", default=".", help="project folder (default: current folder)")
    parser.add_argument("--tail", type=int, default=15, help="lines of output to show on failure")
    parser.add_argument("--max-errors", type=int, default=15, help="error-looking lines to show on failure")
    parser.add_argument("--timeout", type=int, default=600, help="seconds before the gate is stopped")
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

    result = run_gate(args.shell or command, args.task, args.name, args.root,
                      shell=bool(args.shell), timeout=args.timeout)
    for line in summary(result, tail=args.tail, max_errors=args.max_errors):
        print(line)
    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
