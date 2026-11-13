#!/usr/bin/env python3
"""Change proposals: create, show, link and apply (ADR-0003).

Usage:
    python3 tools/change.py new TITLE [--by NAME] [--json]
    python3 tools/change.py show [ID] [--json]
    python3 tools/change.py link ID --task T [T ...]
    python3 tools/change.py apply ID [--by NAME]
    python3 tools/change.py --root DIR ...

A shipped product changes through ``changes/C<NN>/proposal.md`` (from
``templates/change-proposal.md``): why, what, linked board tasks and deltas per
``file#heading`` (ADDED, MODIFIED, REMOVED). ``apply`` merges the deltas only when
a granted ``scope_change`` approval names the ID in its note and every linked task
is done; a second ``apply`` changes nothing. No external dependencies; the logic
lives in core/changes.py.

Exit codes: 0 ok, 1 refused (unknown ID or task, no approval, task not done,
delta does not apply), 2 usage or no project board.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import changes  # noqa: E402
from core.errors import PolierError  # noqa: E402

__all__ = ["main"]


def _json(value) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _new(args) -> int:
    try:
        change_id = changes.create(args.root, args.title, args.by)
    except PolierError as exc:
        print(f"change.py: {exc}", file=sys.stderr)
        return 2
    path = changes.proposal_path(args.root, change_id).relative_to(args.root).as_posix()
    next_step = (f"fill why, what and the deltas in {path}, then "
                 f"tools/change.py link {change_id} --task <ID> and request a scope_change approval")
    if args.json:
        _json({"id": change_id, "path": path, "status": "draft", "next": next_step})
    else:
        print(f"CHANGE {change_id} created · {path} · status draft")
        print(f"  next: {next_step}")
    return 0


def _summary(root, change_id: str) -> dict:
    proposal = changes.load(root, change_id)
    state = changes.status_of(root, proposal)
    return {"id": proposal["id"] or change_id, "title": proposal["title"],
            "status": proposal["status"], "tasks": proposal["tasks"],
            "open_tasks": state["open_tasks"], "approval": state["approval"],
            "deltas": [f"{d['file']}#{d['heading']} {d['kind']}" for d in proposal["deltas"]],
            "errors": proposal["errors"]}


def _describe(item: dict) -> str:
    tasks = ", ".join(item["tasks"]) or "none"
    lines = [f"{item['id']} · {item['status']} · {item['title']}",
             f"  tasks: {tasks}" + (f" (not done: {', '.join(item['open_tasks'])})"
                                    if item["open_tasks"] else ""),
             f"  approval: {item['approval'] or 'none granted naming ' + item['id']}",
             f"  deltas: {len(item['deltas'])}"]
    lines += [f"    {delta}" for delta in item["deltas"]]
    lines += [f"  problem: {error}" for error in item["errors"]]
    return "\n".join(lines)


def _show(args) -> int:
    try:
        wanted = [args.id] if args.id else changes.ids(args.root)
        items = [_summary(args.root, change_id) for change_id in wanted]
    except PolierError as exc:
        print(f"change.py: {exc}", file=sys.stderr)
        return 1
    if args.json:
        _json(items[0] if args.id else items)
        return 0
    if not items:
        print("NO CHANGE PROPOSALS · next: tools/change.py new TITLE")
        return 0
    print("\n".join(_describe(item) for item in items))
    return 0


def _link(args) -> int:
    try:
        tasks = changes.link(args.root, args.id, args.task)
    except PolierError as exc:
        print(f"change.py: {exc}", file=sys.stderr)
        return 1
    print(f"CHANGE {args.id} linked · tasks: {', '.join(tasks)}")
    print(f"  next: request a scope_change approval naming {args.id}, then start the tasks")
    return 0


def _apply(args) -> int:
    try:
        result = changes.apply(args.root, args.id, args.by)
    except PolierError as exc:
        print(f"change.py: {exc}", file=sys.stderr)
        return 1
    if not result["applied"]:
        print(f"CHANGE {args.id}: {result['note']}")
        return 0
    print(f"CHANGE {args.id} applied by {args.by} · approval {result['approval']}")
    for target in result["changed"]:
        print(f"  changed: {target}")
    if not result["changed"]:
        print("  no deltas")
    print("  next: regenerate STATUS.md and run tools/check.py")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--root", default=".", help="project folder (default: .)")
    sub = parser.add_subparsers(dest="command", required=True)

    def command(name, help_text):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--root", dest="root", default=argparse.SUPPRESS,
                       help="project folder (default: .)")
        return p

    new_p = command("new", "create changes/C<NN>/proposal.md from the template")
    new_p.add_argument("title", help="what changes, in a few words")
    new_p.add_argument("--by", default="owner", help="who asked (default: owner)")
    new_p.add_argument("--json", action="store_true", help="print one JSON object")

    show_p = command("show", "show one proposal, or all of them")
    show_p.add_argument("id", nargs="?", help="proposal ID, e.g. C01")
    show_p.add_argument("--json", action="store_true", help="print JSON")

    link_p = command("link", "link board tasks to a proposal")
    link_p.add_argument("id", help="proposal ID, e.g. C01")
    link_p.add_argument("--task", nargs="+", required=True, help="board task IDs")

    apply_p = command("apply", "merge the deltas into the living docs")
    apply_p.add_argument("id", help="proposal ID, e.g. C01")
    apply_p.add_argument("--by", default="owner", help="who applies it (default: owner)")

    args = parser.parse_args(argv)
    args.root = Path(args.root)
    handlers = {"new": _new, "show": _show, "link": _link, "apply": _apply}
    try:
        return handlers[args.command](args)
    except OSError as exc:
        print(f"change.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
