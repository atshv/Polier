#!/usr/bin/env python3
"""The software factory line: from idea to operation, station by station.

Usage:
    python3 tools/factory.py init --platforms web,ios [--traits accounts,payments] [--by NAME]
    python3 tools/factory.py scope [--platforms …] [--traits …] [--by NAME]
    python3 tools/factory.py status [--json]
    python3 tools/factory.py next [--json] [--limit N]
    python3 tools/factory.py list [--station ID] [--open] [--json]
    python3 tools/factory.py show ITEM [--json]
    python3 tools/factory.py done ITEM --evidence PATH[#heading] [--evidence …] [--by NAME]
    python3 tools/factory.py na ITEM --reason TEXT [--by NAME]
    python3 tools/factory.py defer ITEM --reason TEXT [--by NAME]
    python3 tools/factory.py reopen ITEM [--by NAME]
    python3 tools/factory.py link ITEM --task ID[,ID…] [--replace] [--by NAME]
    python3 tools/factory.py advance --by OWNER [--note TEXT]
    python3 tools/factory.py check [--json]
    python3 tools/factory.py render [--stdout]
    python3 tools/factory.py catalog [--platforms …] [--traits …] [--write]
    python3 tools/factory.py --root DIR ...

The catalog of stations and checklist items is factory/catalog.json in this
package; the project's line is factory.json, written only by this tool.
``render`` writes docs/factory.md. ``catalog --write`` regenerates the
package's factory/CATALOG.md. The logic lives in core/factory.py.

Exit codes: 0 ok, 1 refused (an item or station does not hold, check found
errors), 2 usage or environment error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import factory  # noqa: E402
from core.errors import PolierError  # noqa: E402

__all__ = ["main"]

PACKAGE = Path(__file__).resolve().parent.parent


def _json(value) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _list(value) -> list:
    out = []
    for part in value or []:
        out += [p.strip() for p in str(part).split(",") if p.strip()]
    return out


def _print_status(report: dict) -> None:
    print(f"Platforms: {', '.join(report['platforms'])}")
    print(f"Traits:    {', '.join(report['traits']) or '—'}")
    print(f"Items:     {report['items_resolved']}/{report['items_total']} resolved · "
          f"current station: {report['current'] or 'complete'}")
    print()
    for station in report["stations"]:
        mark = {"done": "✓", "active": "▶", "pending": " "}.get(station["status"], "?")
        counts = f"{station['done']} done, {station['na']} n/a, {station['deferred']} deferred, {station['open']} open"
        if not station["items"]:
            counts = "no applicable items"
        print(f" {mark} {station['id']:<13} {station['role']:<16} {counts}")
    for error in report["errors"]:
        print(f"error: {error}")
    for warning in report["warnings"]:
        print(f"warning: {warning}")


def _print_next(value: dict) -> None:
    if value["station"] is None:
        print("The line is complete: every station is closed.")
        return
    print(f"Station: {value['station']} ({value['title']}) — role: {value['role']}")
    print(f"Goal: {value['goal']}")
    print(f"Outputs: {', '.join(value['outputs'])}")
    if not value["items"]:
        print("No open items. Close the station with: tools/factory.py advance --by <owner>")
        return
    print()
    for item in value["items"]:
        tasks = f" (tasks {', '.join(item['tasks'])})" if item["tasks"] else ""
        print(f"[ ] {item['id']} {item['title']} [{item['level']}]{tasks}")
        print(f"    {item['detail']}")
        print(f"    evidence: {item['evidence']}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Polier software factory line.")
    parser.add_argument("--root", default=".", help="project folder (default: .)")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, help_text):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--root", dest="root", default=argparse.SUPPRESS, help="project folder (default: .)")
        return p

    p = add("init", "start the line: platforms, traits, applicable items")
    p.add_argument("--platforms", action="append", required=True, help="comma list, e.g. web,ios")
    p.add_argument("--traits", action="append", default=[], help="comma list, e.g. accounts,payments")
    p.add_argument("--by", help="who starts it")
    p.add_argument("--force", action="store_true", help="overwrite an existing factory.json")

    p = add("scope", "change platforms or traits")
    p.add_argument("--platforms", action="append")
    p.add_argument("--traits", action="append")
    p.add_argument("--by")

    p = add("status", "stations and progress")
    p.add_argument("--json", action="store_true")

    p = add("next", "open items of the current station")
    p.add_argument("--json", action="store_true")
    p.add_argument("--limit", type=int, default=0)

    p = add("list", "items with their status")
    p.add_argument("--station")
    p.add_argument("--open", action="store_true", help="only open items")
    p.add_argument("--json", action="store_true")

    p = add("show", "one item")
    p.add_argument("item")
    p.add_argument("--json", action="store_true")

    p = add("done", "mark an item done with evidence")
    p.add_argument("item")
    p.add_argument("--evidence", action="append", default=[], help="project path, optionally #heading; repeatable")
    p.add_argument("--note")
    p.add_argument("--by")

    for name, text in (("na", "mark an item not applicable"), ("defer", "defer a should item")):
        p = add(name, text)
        p.add_argument("item")
        p.add_argument("--reason", required=True)
        p.add_argument("--by")

    p = add("reopen", "set an item back to open")
    p.add_argument("item")
    p.add_argument("--by")

    p = add("link", "link board tasks that deliver an item")
    p.add_argument("item")
    p.add_argument("--task", action="append", required=True, help="task ID(s), comma list or repeated")
    p.add_argument("--replace", action="store_true", help="replace the linked tasks instead of adding")
    p.add_argument("--by")

    p = add("advance", "close the current station (owner decision) and open the next")
    p.add_argument("--by", required=True, help="owner who approves the station")
    p.add_argument("--note")

    p = add("check", "validate factory.json against the catalog, the board and the files")
    p.add_argument("--json", action="store_true")

    p = add("render", "write docs/factory.md")
    p.add_argument("--stdout", action="store_true", help="print instead of writing")

    p = add("catalog", "print the catalog, optionally for one scope")
    p.add_argument("--platforms", action="append")
    p.add_argument("--traits", action="append", default=[])
    p.add_argument("--write", action="store_true", help="regenerate factory/CATALOG.md in the package")

    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    try:
        if args.command == "init":
            data = factory.init(root, _list(args.platforms), _list(args.traits), by=args.by, force=args.force)
            print(f"factory.json written: {len(data['items'])} items for {', '.join(data['platforms'])}")
            print(f"traits: {', '.join(data['resolved_traits']) or '—'}")
            print("next: tools/factory.py next")
            return 0
        if args.command == "scope":
            result = factory.rescope(root, _list(args.platforms) if args.platforms is not None else None,
                                     _list(args.traits) if args.traits is not None else None, by=args.by)
            print(f"scope: {', '.join(result['platforms'])} · traits {', '.join(result['traits']) or '—'}")
            print(f"added: {', '.join(result['added']) or 'none'}")
            print(f"now n/a: {', '.join(result['dropped']) or 'none'}")
            return 0
        if args.command == "status":
            report = factory.evaluate(root)
            if args.json:
                _json(report)
            else:
                _print_status(report)
            return 0
        if args.command == "next":
            value = factory.next_items(root, limit=args.limit)
            if args.json:
                _json(value)
            else:
                _print_next(value)
            return 0
        if args.command == "list":
            data = factory.need(root)
            catalog = factory.load_catalog()
            rows = []
            for item in catalog["items"]:
                entry = (data.get("items") or {}).get(item["id"])
                if entry is None or (args.station and item["station"] != args.station):
                    continue
                if args.open and entry.get("status") != "open":
                    continue
                rows.append({"id": item["id"], "station": item["station"], "level": item["level"],
                             "title": item["title"], "status": entry.get("status"),
                             "tasks": factory.linked_tasks(entry), "evidence": entry.get("evidence") or [],
                             "reason": entry.get("reason")})
            if args.json:
                _json(rows)
            else:
                for row in rows:
                    mark = factory.STATUS_MARK.get(row["status"], "[?]")
                    tail = f" · tasks {', '.join(row['tasks'])}" if row["tasks"] else ""
                    print(f"{mark} {row['id']:<11} {row['station']:<13} {row['title']}{tail}")
            return 0
        if args.command == "show":
            item = factory.catalog_item(args.item)
            data = factory.load(root)
            entry = (data or {}).get("items", {}).get(item["id"])
            value = {**item, "applies": entry is not None, "state": entry,
                     "problems": factory.item_problems(root, item["id"], entry) if entry else []}
            if args.json:
                _json(value)
            else:
                print(f"{item['id']} {item['title']} [{item['level']}] — station {item['station']}")
                print(f"  {item['detail']}")
                print(f"  applies to: {', '.join((item.get('platforms') or []) + (item.get('traits') or [])) or 'all'}")
                print(f"  evidence: {item['evidence']}")
                if entry is None:
                    print("  not part of this project's scope")
                else:
                    print(f"  status: {entry.get('status')}")
                    for key in ("tasks", "evidence", "reason", "note"):
                        if entry.get(key):
                            shown = entry[key] if isinstance(entry[key], str) else ", ".join(entry[key])
                            print(f"  {key}: {shown}")
                    for problem in value["problems"]:
                        print(f"  problem: {problem}")
            return 0
        if args.command == "done":
            entry = factory.set_item(root, args.item, "done", evidence=args.evidence, reason=args.note, by=args.by)
            print(f"{args.item.upper()} done · {', '.join(entry.get('evidence') or factory.linked_tasks(entry))}")
            return 0
        if args.command in ("na", "defer"):
            status = "na" if args.command == "na" else "deferred"
            factory.set_item(root, args.item, status, reason=args.reason, by=args.by)
            print(f"{args.item.upper()} {status}: {args.reason}")
            return 0
        if args.command == "reopen":
            factory.set_item(root, args.item, "open", by=args.by)
            print(f"{args.item.upper()} open")
            return 0
        if args.command == "link":
            entry = factory.link(root, args.item, _list(args.task), by=args.by, replace=args.replace)
            print(f"{args.item.upper()} → {', '.join(entry['tasks'])}")
            return 0
        if args.command == "advance":
            result = factory.advance(root, args.by, note=args.note)
            print(f"closed: {', '.join(result['closed'])}")
            print(f"now active: {result['opened'] or 'none — the line is complete'}")
            return 0
        if args.command == "check":
            report = factory.evaluate(root)
            if args.json:
                _json({"errors": report["errors"], "warnings": report["warnings"]})
            else:
                for error in report["errors"]:
                    print(f"error: {error}")
                for warning in report["warnings"]:
                    print(f"warning: {warning}")
                if not report["errors"]:
                    print(f"factory ok · {report['items_resolved']}/{report['items_total']} items resolved · "
                          f"station {report['current'] or 'complete'}")
            return 1 if report["errors"] else 0
        if args.command == "render":
            text = factory.render_markdown(root)
            if args.stdout:
                sys.stdout.write(text)
            else:
                target = root / "docs" / "factory.md"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
                print(f"written: {target.relative_to(root).as_posix()}")
            return 0
        if args.command == "catalog":
            if args.platforms is not None:
                text = factory.catalog_markdown(_list(args.platforms), _list(args.traits))
            else:
                text = factory.catalog_markdown()
            if args.write:
                target = PACKAGE / "factory" / "CATALOG.md"
                target.write_text(text, encoding="utf-8")
                print(f"written: {target}")
            else:
                sys.stdout.write(text)
            return 0
    except PolierError as exc:
        message = str(exc)
        print(f"error: {message}", file=sys.stderr)
        refused = args.command in ("done", "na", "defer", "reopen", "advance", "link")
        return 1 if refused and "no factory.json" not in message and "unknown" not in message else 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
