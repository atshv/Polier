#!/usr/bin/env python3
"""Run one headless agent session for a task, from the CLI (2.0).

Usage:
    python3 tools/session.py run M03 --role worker [--root .] [--worktree] [--note "..."] [--json]
    python3 tools/session.py list [--json]
    python3 tools/session.py show <session-id>
    python3 tools/session.py stop <session-id>

The session uses the dashboard's provider settings
(``<git-common-dir>/polier/dashboard/config.json`` → ``session``): the command,
permission mode, allowed tools, model and environment. The prompt is composed
from the task brief and the role, exactly like a dashboard session; the run
records its token use in ``runs/<ID>.json``.

Exit codes: 0 session finished successfully, 1 session failed or stopped,
2 usage or environment error.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import runtime  # noqa: E402
from core.errors import PolierError  # noqa: E402
from server.sessions import SessionManager  # noqa: E402


def _manager(root: Path) -> SessionManager:
    config = runtime.read_json(runtime.runtime_dir(root) / "config.json").get("session") or {}
    return SessionManager(root, bus=None, config=config)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="start one session and wait for it")
    run.add_argument("task", nargs="?", help="task ID (omit for a generator/review session)")
    run.add_argument("--role", default="worker", choices=("worker", "reviewer", "lead", "generator"))
    run.add_argument("--root", default=".", help="project folder (default: .)")
    run.add_argument("--worktree", action="store_true", help="run in a fresh task worktree")
    run.add_argument("--note", default=None, help="extra instructions for the agent")
    run.add_argument("--prompt-file", default=None, help="use this prompt instead of the composed one")
    run.add_argument("--max-tokens", type=int, default=None, help="stop waiting after this many tokens")
    run.add_argument("--json", action="store_true", help="print the final session record as JSON")
    listing = sub.add_parser("list", help="list the sessions of this project")
    listing.add_argument("--root", default=".")
    listing.add_argument("--json", action="store_true")
    show = sub.add_parser("show", help="show one session")
    show.add_argument("session")
    show.add_argument("--root", default=".")
    stop = sub.add_parser("stop", help="stop a running session")
    stop.add_argument("session")
    stop.add_argument("--root", default=".")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    manager = _manager(root)
    if args.command == "list":
        sessions = manager.list()
        if args.json:
            print(json.dumps(sessions, indent=2))
        else:
            for session in sessions:
                print(f"{session['id']}  {session['status']:8s}  {session.get('role') or '':8s}  "
                      f"{session.get('task') or '-':10s}  {session.get('tokens') or 0} tokens")
        return 0
    if args.command == "show":
        try:
            print(json.dumps(manager.get(args.session), indent=2))
        except KeyError:
            print(f"session.py: unknown session {args.session}", file=sys.stderr)
            return 2
        return 0
    if args.command == "stop":
        try:
            print(json.dumps(manager.stop(args.session), indent=2))
        except KeyError:
            print(f"session.py: unknown session {args.session}", file=sys.stderr)
            return 2
        return 0

    prompt = None
    if args.prompt_file:
        try:
            prompt = Path(args.prompt_file).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"session.py: cannot read prompt file: {exc}", file=sys.stderr)
            return 2
    try:
        session = manager.start(task=args.task, role=args.role, prompt=prompt, note=args.note,
                                worktree=args.worktree)
    except PolierError as exc:
        print(f"session.py: {exc}", file=sys.stderr)
        return 2
    session_id = session["id"]
    print(f"session {session_id} ({args.role}) started"
          + (f" for {args.task}" if args.task else "") + " …", file=sys.stderr)
    seen = 0
    while True:
        current = manager.get(session_id)
        log = manager.log(session_id, seen)
        if log.get("text"):
            sys.stdout.write(log["text"])
            sys.stdout.flush()
            seen = int(log.get("next") or seen)
        if current["status"] not in ("starting", "running"):
            break
        if args.max_tokens and int(current.get("tokens") or 0) >= args.max_tokens:
            manager.stop(session_id)
            print(f"session.py: token limit {args.max_tokens} reached; stopping", file=sys.stderr)
        time.sleep(0.4)
    final = manager.get(session_id)
    if args.json:
        print(json.dumps(final, indent=2))
    print(f"session {session_id} {final['status']}"
          + (f" (exit {final.get('exit_code')})" if final.get("exit_code") is not None else "")
          + f", {final.get('tokens') or 0} tokens", file=sys.stderr)
    return 0 if final["status"] == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
