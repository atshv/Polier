#!/usr/bin/env python3
"""Import-boundary gate between the packages of a Polier monorepo (PL-07).

Usage:
    python3 tools/boundaries.py examples/monorepo-mini
    python3 tools/boundaries.py /path/to/project --json

Reads the package map from <root>/board.json. Exit 0 = no cross-package
violation, 1 = at least one violation, 2 = configuration or usage error
(no board, invalid JSON, no packages, bad arguments). Standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.board import load_board  # noqa: E402
from core.boundaries import find_violations  # noqa: E402
from core.errors import PolierError  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="boundaries.py",
        description="Check cross-package imports against packages[].may_import.",
    )
    parser.add_argument("root", nargs="?", default=".", help="project root (default: .)")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"ERROR: project root not found: {root}", file=sys.stderr)
        return 2
    try:
        board = load_board(root)
    except PolierError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if not isinstance(board, dict) or not board.get("packages"):
        print("ERROR: board.json declares no packages; add packages[] before using the "
              "boundaries gate", file=sys.stderr)
        return 2

    result = find_violations(root, board)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        for warning in result["warnings"]:
            print(f"WARN: {warning}")
        for violation in result["violations"]:
            print(
                f"{violation['file']}:{violation['line']} "
                f"{violation['from_package']} -> {violation['to_package']} "
                f"({violation['specifier']})"
            )
        suffix = f" ({len(result['warnings'])} warning(s))" if result["warnings"] else ""
        if result["violations"]:
            print(f"FAIL: {len(result['violations'])} boundary violation(s) in {root}{suffix}")
        else:
            print(f"OK: {root}: {len(result['packages'])} package(s) respect the import "
                  f"boundaries{suffix}")
    return 1 if result["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
