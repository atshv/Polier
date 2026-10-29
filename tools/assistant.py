#!/usr/bin/env python3
"""Ask the project assistant and read its conversations (2.4).

Usage:
    python3 tools/assistant.py ask "What is blocking stage 7?" [--conversation conv-…] [--json]
    python3 tools/assistant.py list [--json]
    python3 tools/assistant.py show <conversation-id> [--json]
    python3 tools/assistant.py delete <conversation-id>

The assistant is one headless agent session with a read-only briefing (plan,
blocked tasks, approvals, recent activity, task list) and a structured proposal
block. It never changes the project; proposals are printed and can be applied
from the dashboard. Provider settings come from the dashboard config (same as
`tools/session.py`). Exit 0 answered, 1 failed/unknown, 2 usage error.
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
from server.assistant import AssistantManager  # noqa: E402
from server.sessions import SessionManager  # noqa: E402


def _print(value) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _manager(root: Path) -> AssistantManager:
    config = runtime.read_json(runtime.runtime_dir(root) / "config.json").get("session") or {}
    sessions = SessionManager(root, bus=None, config=config)
    return AssistantManager(root, sessions, bus=None)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="project folder (default: .)")
    sub = parser.add_subparsers(dest="command", required=True)
    ask = sub.add_parser("ask", help="ask one question and wait for the answer")
    ask.add_argument("question")
    ask.add_argument("--conversation", help="continue an existing conversation")
    ask.add_argument("--json", action="store_true")
    ask.add_argument("--timeout", type=int, default=300)
    listing = sub.add_parser("list", help="list conversations")
    listing.add_argument("--json", action="store_true")
    show = sub.add_parser("show", help="show one conversation")
    show.add_argument("conversation")
    show.add_argument("--json", action="store_true")
    delete = sub.add_parser("delete", help="delete a conversation")
    delete.add_argument("conversation")
    for child in sub.choices.values():
        child.add_argument("--root", default=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    manager = _manager(Path(args.root))
    if args.command == "list":
        values = manager.list()
        _print({"conversations": values}) if args.json else [
            print(f"{item['id']}  {item.get('updated')}  {item.get('title')}") for item in values]
        return 0
    if args.command == "show":
        try:
            _print(manager.get(args.conversation))
            return 0
        except KeyError:
            print("assistant.py: unknown conversation", file=sys.stderr)
            return 1
    if args.command == "delete":
        try:
            _print(manager.delete(args.conversation))
            return 0
        except KeyError:
            print("assistant.py: unknown conversation", file=sys.stderr)
            return 1
    try:
        conversation = manager.start(args.question, args.conversation)
    except KeyError:
        print("assistant.py: unknown conversation", file=sys.stderr)
        return 1
    except PolierError as exc:
        print(f"assistant.py: {exc}", file=sys.stderr)
        return 2
    conversation_id = conversation["id"]
    print(f"assistant: conversation {conversation_id} …", file=sys.stderr)
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        current = manager.get(conversation_id)
        if not current.get("pending"):
            break
        time.sleep(0.4)
    final = manager.get(conversation_id)
    if args.json:
        _print(final)
        return 0 if not final.get("pending") else 1
    messages = final.get("messages") or []
    for message in messages[-2:]:
        print(f"{message.get('role')}: {message.get('content')}")
        for proposal in message.get("proposals") or []:
            print(f"  proposal [{proposal.get('kind')}] {proposal.get('title')}: {proposal.get('reason')}")
    return 0 if not final.get("pending") else 1


if __name__ == "__main__":
    sys.exit(main())
