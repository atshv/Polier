#!/usr/bin/env python3
"""Error classes over the records of Polier projects; reads, never writes into them.

Usage:
    python3 tools/retro.py FOLDER... [--json] [--write PATH] [--since YYYY-MM-DD]

Prints a Markdown report (or one JSON object with classes[] and skipped[]) with
each error class that has a signal: count, example records and the Polier file
it points at. `--write PATH` writes the report there instead of stdout and
refuses a PATH inside a given folder.

Exit codes: 0 report produced, 1 no folder had records, 2 usage (unknown
folder, bad date, refused PATH). The logic lives in core/retro.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.errors import PolierError  # noqa: E402
from core.retro import has_records, parse_since, report  # noqa: E402

__all__ = ["main"]


def _markdown(result: dict) -> str:
    lines = ["# Retro", ""]
    if not result["classes"]:
        lines += ["No error class has a signal in the records read.", ""]
    for entry in result["classes"]:
        lines += [f"## {entry['class']} ({entry['count']})", "",
                  f"Points at: {', '.join(f'`{p}`' for p in entry['points_at'])}", ""]
        lines += [f"- `{ex['record']}`: {ex['detail']}" for ex in entry["examples"]]
        lines.append("")
    if result["skipped"]:
        lines += ["## Skipped", ""]
        lines += [f"- {s['folder']}: {s['reason']}" for s in result["skipped"]]
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("folders", nargs="+", metavar="FOLDER")
    parser.add_argument("--json", action="store_true", help="print one JSON object")
    parser.add_argument("--write", metavar="PATH", help="write the report to PATH")
    parser.add_argument("--since", metavar="YYYY-MM-DD", help="ignore records dated before this day")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    try:
        since = parse_since(args.since) if args.since else None
        for folder in args.folders:
            if not Path(folder).is_dir():
                raise PolierError(f"{folder} is not a folder")
        if args.write:
            target = Path(args.write).resolve()
            for folder in args.folders:
                root = Path(folder).resolve()
                if target == root or root in target.parents:
                    raise PolierError(f"--write PATH {args.write} is inside {folder}; the retro never writes there")
        result = report(args.folders, since)
    except PolierError as exc:
        print(f"retro.py: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(result, indent=2, sort_keys=True) if args.json else _markdown(result)
    if args.write:
        try:
            Path(args.write).write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"retro.py: {exc}", file=sys.stderr)
            return 2
        print(f"retro.py: report written to {args.write}", file=sys.stderr)
    else:
        print(text)
    return 0 if any(has_records(f) for f in args.folders) else 1


if __name__ == "__main__":
    raise SystemExit(main())
