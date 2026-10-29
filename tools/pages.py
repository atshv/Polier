#!/usr/bin/env python3
"""Browse the project's Markdown pages from the CLI (2.3).

Usage:
    python3 tools/pages.py list [--json]
    python3 tools/pages.py search "contract version" [--limit 20] [--json]
    python3 tools/pages.py show docs/contracts.md [--ref <commit>] [--json]
    python3 tools/pages.py history docs/contracts.md [--json]
    python3 tools/pages.py favorite add|remove docs/contracts.md
    python3 tools/pages.py favorites

The same read-only model the dashboard uses (core/pages.py): collections from the
project layout (root, docs, tasks, reviews, package docs), content, safe links,
backlinks, git history and local favorites. Exit 2 on usage errors, 1 on an
unknown page.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import pages  # noqa: E402
from core.errors import PolierError  # noqa: E402


def _print(value) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _subparsers(parser):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    return {}


def _add_root_options(sub) -> None:
    for child in sub.choices.values():
        child.add_argument("--root", default=argparse.SUPPRESS)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="project folder (default: .)")
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", help="collections and pages")
    listing.add_argument("--json", action="store_true")
    search = sub.add_parser("search", help="full-text page search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=50)
    search.add_argument("--json", action="store_true")
    show = sub.add_parser("show", help="one page")
    show.add_argument("path")
    show.add_argument("--ref", help="read a git revision of the page")
    show.add_argument("--json", action="store_true")
    history = sub.add_parser("history", help="git history of a page")
    history.add_argument("path")
    history.add_argument("--json", action="store_true")
    favorite = sub.add_parser("favorite", help="add or remove a favorite")
    favorite.add_argument("action", choices=("add", "remove"))
    favorite.add_argument("path")
    favorites = sub.add_parser("favorites", help="list favorites")
    favorites.add_argument("--json", action="store_true")
    _add_root_options(sub)
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        if args.command == "list":
            value = pages.index(root)
            if args.json:
                _print(value)
            else:
                for collection in value["collections"]:
                    print(f"[{collection['id']}] {collection['title']}")
                    for page in collection["pages"]:
                        print(f"  {page['path']}  ({page['words']} words)")
        elif args.command == "search":
            results = pages.search(root, args.query, args.limit)
            if args.json:
                _print({"query": args.query, "results": results})
            else:
                for result in results:
                    print(f"{result['path']}  score {result['score']}  {result['title']}")
        elif args.command == "show":
            value = pages.page(root, args.path, args.ref)
            if args.json:
                _print(value)
            else:
                print(value["text"])
        elif args.command == "history":
            value = pages.history(root, args.path)
            if args.json:
                _print({"path": args.path, "history": value})
            else:
                for commit in value:
                    print(f"{commit['hash']}  {commit['date']}  {commit['subject']}")
        elif args.command == "favorite":
            current = pages.load_favorites(root)["favorites"]
            if args.action == "add":
                if args.path not in current:
                    current.append(args.path)
            else:
                current = [entry for entry in current if entry != args.path]
            _print(pages.set_favorites(root, current))
        elif args.command == "favorites":
            value = pages.load_favorites(root)
            _print(value) if args.json else print("\n".join(value["favorites"]))
    except KeyError:
        print("pages.py: unknown page", file=sys.stderr)
        return 1
    except PolierError as exc:
        print(f"pages.py: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
