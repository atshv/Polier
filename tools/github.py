#!/usr/bin/env python3
"""Read-only GitHub/CI status for the project (2.4).

Usage:
    python3 tools/github.py status [--json] [--force]
    python3 tools/github.py auth [--json]        # is gh signed in, as whom, which scopes

Uses the project's GitHub ``origin`` and the authenticated ``gh`` CLI. The output
maps pull requests and workflow runs to tasks by branch (``task/<ID>`` or the
task's branch). Without ``gh`` or a GitHub remote the command explains why it is
unavailable (exit 0, available=false). No credentials are read or stored.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import github  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="project folder (default: .)")
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="PRs, CI runs and task mapping")
    status.add_argument("--json", action="store_true")
    status.add_argument("--force", action="store_true")
    auth = sub.add_parser("auth", help="the GitHub account connection of the gh CLI")
    auth.add_argument("--json", action="store_true")
    for child in sub.choices.values():
        child.add_argument("--root", default=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.command == "auth":
        value = github.auth_status()
        if args.json:
            print(json.dumps(value, indent=2, ensure_ascii=False))
        elif value.get("logged_in"):
            print(f"github: connected as {value.get('user')} (scopes: {', '.join(value.get('scopes') or []) or '-'})")
        else:
            print(f"github: not connected — {value.get('reason')}. Run: gh auth login --web")
        return 0 if value.get("logged_in") else 1
    value = github.status(root, force=getattr(args, "force", False))
    if args.json:
        print(json.dumps(value, indent=2, ensure_ascii=False))
    elif not value.get("available"):
        print(f"github: unavailable — {value.get('reason')}")
    else:
        print(f"github: {value['repo']}  ({value['counts']['prs']} open PR(s), "
              f"{value['counts']['runs']} recent run(s))")
        for pr in value.get("prs") or []:
            print(f"  #{pr.get('number')} [{pr.get('checks')}] {pr.get('title')}  {pr.get('url')}")
        for run in value.get("runs") or []:
            print(f"  {run.get('name')}: {run.get('status')} {run.get('conclusion') or ''} "
                  f"{run.get('headBranch')}  {run.get('url')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
