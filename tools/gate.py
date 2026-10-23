#!/usr/bin/env python3
"""Run one gate command, keep the full output in a log file, print only a short result.

Usage:
    python3 tools/gate.py --task M03 --name tests -- pytest -q
    python3 tools/gate.py --task M03 --name lint --root /path/to/project -- ruff check .

The full output goes to <root>/reviews/evidence/<task>-<name>.log.
On success only one line is printed. On failure the last lines and the lines that
look like errors are printed too. Exit code is the gate's own exit code
(124 on timeout). No external dependencies.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ERROR_LINE = re.compile(r"error|fail|traceback|exception|assert|panic|fatal", re.IGNORECASE)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--task", required=True, help="task ID, e.g. M03")
    parser.add_argument("--name", required=True, help="gate name, e.g. tests")
    parser.add_argument("--root", default=".", help="project folder (default: current folder)")
    parser.add_argument("--tail", type=int, default=15, help="lines of output to show on failure")
    parser.add_argument("--max-errors", type=int, default=15, help="error-looking lines to show on failure")
    parser.add_argument("--timeout", type=int, default=600, help="seconds before the gate is stopped")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="gate command after --")
    args = parser.parse_args()

    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("gate command missing: put it after --")

    root = Path(args.root).resolve()
    log = root / "reviews" / "evidence" / f"{args.task}-{args.name}.log"
    log.parent.mkdir(parents=True, exist_ok=True)

    shown = " ".join(" ".join(command).split())
    try:
        result = subprocess.run(
            command, cwd=root, capture_output=True, text=True,
            timeout=args.timeout, check=False,
        )
        code = result.returncode
        output = (result.stdout or "") + (result.stderr or "")
    except subprocess.TimeoutExpired as exc:
        code = 124
        output = ((exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""))
        output += f"\n[gate.py] stopped after {args.timeout}s\n"
    except FileNotFoundError:
        code = 127
        output = f"[gate.py] command not found: {command[0]}\n"

    log.write_text(f"$ {shown}\n[exit {code}]\n\n{output}", encoding="utf-8")
    rel = log.relative_to(root)
    lines = output.splitlines()

    if code == 0:
        print(f"GATE {args.name}: PASS (exit 0) — {len(lines)} lines in {rel}")
        return 0

    print(f"GATE {args.name}: FAIL (exit {code}) — {shown}")
    errors = [line for line in lines if ERROR_LINE.search(line)]
    if errors:
        print(f"-- first {min(len(errors), args.max_errors)} of {len(errors)} error lines")
        for line in errors[: args.max_errors]:
            print(line[:300])
    print(f"-- last {min(len(lines), args.tail)} lines")
    for line in lines[-args.tail:]:
        print(line[:300])
    print(f"-- full output: {rel}")
    return code


if __name__ == "__main__":
    sys.exit(main())
