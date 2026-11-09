#!/usr/bin/env python3
"""Preflight: is everything in place before work starts or continues?

Usage:
    python3 tools/preflight.py [folder] [--json]

Checks Python, git, the Polier package and, inside a project, git state,
factory.json, board.json, policy.json, STATUS.md and claims. Changes nothing.
Exit 0 = ok or warnings only, 1 = at least one check failed.
The checks live in core/preflight.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.preflight import run  # noqa: E402

MARK = {"ok": "OK  ", "warn": "WARN", "fail": "FAIL"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("folder", nargs="?", default=".")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args(argv)
    result = run(Path(args.folder))
    if args.json:
        print(json.dumps(result))
    else:
        for check in result["checks"]:
            line = f"{MARK[check['level']]} {check['check']}: {check['detail']}"
            if check.get("fix"):
                line += f"\n     fix: {check['fix']}"
            print(line)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
