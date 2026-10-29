#!/usr/bin/env python3
"""Deterministic automations from the CLI (2.4).

Usage:
    python3 tools/automations.py list [--json]
    python3 tools/automations.py validate
    python3 tools/automations.py run [--json]
    python3 tools/automations.py save --json <file>|-     # write automations.json
    python3 tools/automations.py init                      # example rules

Rules live in committed ``automations.json``; ``run`` is a dry run: it prints the
matched rules and suggested actions and changes nothing. Apply a suggestion in
the dashboard (state transition, session) where it is validated by the normal
API. Exit 0 ok, 1 invalid/refused, 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import automations  # noqa: E402
from core.errors import PolierError  # noqa: E402

EXAMPLE = {
    "version": 1,
    "rules": [
        {"id": "gate-failed", "name": "A failed gate needs attention", "enabled": True,
         "when": {"kind": "gate_failed"},
         "actions": [{"type": "state", "status": "blocked",
                      "note": "A gate failed; fix it before continuing."},
                     {"type": "open"}]},
        {"id": "review-waiting", "name": "A task waits for review", "enabled": True,
         "when": {"kind": "review_ready"},
         "actions": [{"type": "session", "role": "reviewer",
                      "note": "Review the diff, the acceptance criteria and the gate records."}]},
        {"id": "stage-decision", "name": "A completed stage needs an owner decision", "enabled": True,
         "when": {"kind": "stage_decision_pending"},
         "actions": [{"type": "open"}]},
    ],
}


def _print(value) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="project folder (default: .)")
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", help="list rules")
    listing.add_argument("--json", action="store_true")
    sub.add_parser("validate", help="validate automations.json")
    run = sub.add_parser("run", help="dry-run the rules")
    run.add_argument("--json", action="store_true")
    save = sub.add_parser("save", help="write automations.json from JSON")
    save.add_argument("--json", required=True)
    init = sub.add_parser("init", help="write the example rules")
    init.add_argument("--force", action="store_true")
    for child in sub.choices.values():
        child.add_argument("--root", default=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        if args.command == "list":
            value = automations.load(root, strict=True)
            _print(value) if args.json else [
                print(f"{rule.get('id')}  {'on' if rule.get('enabled', True) else 'off'}  {rule.get('name')}")
                for rule in value.get("rules") or []]
        elif args.command == "validate":
            value = automations.load(root, strict=True)
            print(f"automations: {len(value.get('rules') or [])} rule(s), valid")
        elif args.command == "run":
            value = automations.evaluate(root)
            if args.json:
                _print(value)
            else:
                print(f"dry run: {value['total']} match(es)")
                for match in value["matches"]:
                    print(f"- {match['rule']}: {match['event'].get('detail')}")
                    for action in match["actions"]:
                        print(f"    {action.get('type')}: {action.get('status') or action.get('role') or action.get('text') or ''}")
        elif args.command == "save":
            text = sys.stdin.read() if args.json == "-" else Path(args.json).read_text(encoding="utf-8")
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise PolierError("automations.json must be an object")
            _print(automations.save(root, payload))
        elif args.command == "init":
            target = automations.path(root)
            if target.exists() and not args.force:
                raise PolierError(f"{target.name} exists; use --force to replace it")
            _print(automations.save(root, EXAMPLE))
    except PolierError as exc:
        print(f"automations.py: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"automations.py: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
