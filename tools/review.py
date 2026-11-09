#!/usr/bin/env python3
"""The review packet of one task as JSON: brief, earlier verdicts, latest gate record per gate, changed files and diff.

Usage:
    python3 tools/review.py [project] [--task M03]

Exit 0 = packet printed, 2 = no board, no unique task or no git repository.
The rules live in core/review.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.errors import PolierError  # noqa: E402
from core.review import packet  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument("--task", help="task ID; default: the one task in progress")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(packet(Path(args.project).resolve(), args.task)))
    except PolierError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
