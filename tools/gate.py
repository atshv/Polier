#!/usr/bin/env python3
"""Run one gate command, keep the full output in a log file, print only a short result.

Usage:
    python3 tools/gate.py --task M03 --name tests -- pytest -q
    python3 tools/gate.py --task M03 --name lint --root /path/to/project -- ruff check .
    python3 tools/gate.py --task M03 --name smoke --shell "bm add x && bm list"

The full output goes to <root>/reviews/evidence/<task>-<name>.log.
On success only one line is printed. On failure the last lines and the lines that
look like errors are printed too. Exit code is the gate's own exit code
(124 on timeout). No external dependencies.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

def git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None
    return result.stdout if result.returncode == 0 else None


def new_base(folder: Path, stem: str) -> Path:
    """A path stem in `folder` for which neither .log nor .json exists yet."""
    base = folder / stem
    n = 2
    while (folder / f"{base.name}.log").exists() or (folder / f"{base.name}.json").exists():
        base = folder / f"{stem}-{n}"
        n += 1
    return base


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


ERROR_LINE = re.compile(r"error|fail|traceback|exception|assert|panic|fatal", re.IGNORECASE)


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
    if args.shell:
        command = [args.shell]
    if not command:
        parser.error("gate command missing: put it after --")

    root = Path(args.root).resolve()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.task) or not re.fullmatch(r"[A-Za-z0-9_.-]+", args.name):
        parser.error("--task and --name may only contain letters, digits, '.', '_' and '-'")
    folder = root / "reviews" / "evidence"
    folder.mkdir(parents=True, exist_ok=True)
    started = dt.datetime.now(dt.timezone.utc)
    base = new_base(folder, f"{args.task}-{args.name}-{started.strftime('%Y%m%dT%H%M%SZ')}")
    log, record_path = folder / f"{base.name}.log", folder / f"{base.name}.json"
    commit = (git(root, "rev-parse", "HEAD") or "").strip() or None
    status = git(root, "status", "--porcelain")

    shown = " ".join(" ".join(command).split())
    try:
        result = subprocess.run(
            command[0] if args.shell else command, cwd=root, capture_output=True, text=True,
            timeout=args.timeout, check=False, shell=bool(args.shell),
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

    finished = dt.datetime.now(dt.timezone.utc)
    log.write_text(f"$ {shown}\n[exit {code}]\n\n{output}", encoding="utf-8")
    record = {
        "task": args.task,
        "gate": args.name,
        "command": shown,
        "exit_code": code,
        "started": started.isoformat(timespec="seconds"),
        "finished": finished.isoformat(timespec="seconds"),
        "commit": commit,
        "dirty": bool(status.strip()) if status is not None else None,
        "log": log.name,
        "log_sha256": sha256(log),
    }
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    rel = log.relative_to(root)
    rel_record = record_path.relative_to(root).as_posix()
    lines = output.splitlines()

    if code == 0:
        print(f"GATE {args.name}: PASS (exit 0) — {len(lines)} lines in {rel}")
        print(f"record: {rel_record}")
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
    print(f"record: {rel_record}")
    return code


if __name__ == "__main__":
    sys.exit(main())
