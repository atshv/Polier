#!/usr/bin/env python3
"""Post-deploy smoke check: fetch a few URLs, expect a status, and record the result.

Usage:
    python3 tools/smoke.py --url http://127.0.0.1:4100 --path /login --path /
    python3 tools/smoke.py --url https://preview.example.com --expect-status 200 \
        --path / --header "Authorization: env:PREVIEW_TOKEN" --task PL-11 --name smoke

Each `--path` is requested against `--url` (joined like a URL). The first
failing path prints the status code and the first 300 bytes of the body and
makes the run exit 1. The result is written as a gate record via core/gate.py
in <root>/reviews/evidence/, so it counts as evidence like any other gate and
is classified as `infra` when the failure is a connection problem.

Header values are never taken from the command line in clear text: the form is
`--header "Name: env:VARIABLE"` (or `Name=env:VARIABLE`), and the value is read
from the environment, so a token does not end up in shell history or the record.

Exit codes: 0 all paths ok, 1 a path failed, 2 usage or configuration error.
No external dependencies. No secret is written to the log.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.board import load_board, pick_task  # noqa: E402
from core.gate import write_record  # noqa: E402

# Failures that are infrastructure, not a broken deployment (same defaults as core/gate.py).
INFRA = ("ECONNREFUSED", "ERR_CONNECTION_REFUSED", "EADDRINUSE",
         "is already used, make sure that nothing is running on the port",
         "address already in use", "connection refused", "timed out")
HEADER = re.compile(r"^\s*([A-Za-z0-9-]+)\s*[:=]\s*env:([A-Za-z_][A-Za-z0-9_]*)\s*$")


def parse_header(spec: str) -> tuple[str, str]:
    """(name, value) of a `Name: env:VARIABLE` header; ValueError otherwise."""
    match = HEADER.match(spec)
    if not match:
        raise ValueError(
            f"header {spec!r} must have the form 'Name: env:VARIABLE' (values come from the environment)")
    name, variable = match.group(1), match.group(2)
    value = os.environ.get(variable)
    if not value:
        raise ValueError(f"environment variable {variable} for header {name} is not set")
    return name, value


def check_url(url: str, path: str, headers: dict[str, str], expected: int,
              timeout: float) -> tuple[bool, str, str, bool]:
    """(ok, report line, body excerpt, transport_error) for one path."""
    target = urllib.parse.urljoin(url.rstrip("/") + "/", path.lstrip("/"))
    request = urllib.request.Request(target, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            body = response.read(300)
    except urllib.error.HTTPError as error:
        status = error.code
        body = error.read(300)
    except (urllib.error.URLError, OSError, ValueError) as error:
        return False, f"FAIL {path}: {type(error).__name__}: {error}", "", True
    excerpt = body.decode("utf-8", errors="replace").replace("\n", " ")[:300]
    if status == expected:
        return True, f"OK   {path}: {status}", "", False
    return False, f"FAIL {path}: {status} (expected {expected})", excerpt, False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--url", required=True, help="base URL, e.g. https://preview.example.com")
    parser.add_argument("--path", action="append", default=[], help="path to check; repeatable (default /)")
    parser.add_argument("--expect-status", type=int, default=200, help="expected HTTP status (default 200)")
    parser.add_argument("--header", action="append", default=[], metavar="NAME:env:VAR",
                        help="request header; the value is read from an environment variable")
    parser.add_argument("--timeout", type=float, default=10.0, help="seconds per request (default 10)")
    parser.add_argument("--task", help="task ID for the record; default: the task in_progress")
    parser.add_argument("--name", default="smoke", help="gate name for the record (default smoke)")
    parser.add_argument("--root", default=".", help="project folder (default: current folder)")
    parser.add_argument("--no-record", action="store_true", help="only print, write no gate record")
    args = parser.parse_args(argv)

    paths = args.path or ["/"]
    try:
        headers = dict(parse_header(spec) for spec in args.header)
    except ValueError as error:
        print(f"smoke: {error}", file=sys.stderr)
        return 2

    lines: list[str] = [f"$ smoke {args.url} {args.expect_status} " + " ".join(paths)]
    all_ok = True
    infra = False
    for path in paths:
        ok, line, excerpt, transport = check_url(args.url, path, headers, args.expect_status, args.timeout)
        lines.append(line)
        if not ok:
            all_ok = False
            infra = infra or transport
            if excerpt:
                lines.append(f"     body: {excerpt}")
    output = "\n".join(lines) + "\n"

    exit_code = 0 if all_ok else 1
    result = "pass" if all_ok else ("infra" if infra else "fail")
    if not all_ok:
        print("\n".join(lines))
        print("SMOKE FAIL: at least one path did not return the expected status", file=sys.stderr)

    record_path = None
    if not args.no_record:
        root = Path(args.root).resolve()
        task = args.task
        if not task:
            board = load_board(root, strict=False)
            if board is not None:
                try:
                    task = str(pick_task(board).get("id"))
                except Exception:  # noqa: BLE001  no unique task: still run, just cannot record
                    task = None
        if task:
            command = " ".join(["smoke.py", "--url", args.url, "--expect-status", str(args.expect_status),
                                *[f"--path {path}" for path in paths]])
            record = write_record(task, args.name, root, command=command, exit_code=exit_code,
                                  output=output, result=result)
            record_path = record["record_path"].relative_to(root).as_posix()
            print(f"record: {record_path}")
        else:
            print("smoke: no task to record under (pass --task)", file=sys.stderr)

    if all_ok:
        print(f"SMOKE OK: {len(paths)} path(s) returned {args.expect_status}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
