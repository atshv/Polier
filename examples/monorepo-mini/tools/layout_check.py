#!/usr/bin/env python3
"""Project gate: board.json, package folders and contract files agree.

Usage:
    python3 tools/layout_check.py
    python3 tools/layout_check.py --root /path/to/canvas-mini

Exit 0 = layout ok, 1 = findings, 2 = configuration or usage error.
Standard library only; no network, no installs.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_KINDS = {"package", "service", "app", "tool", "infra"}
BUDGETS = {"ARCHITECTURE.md": 400, "AGENTS.md": 200}


def words(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").split())


def normalized(value) -> str:
    return str(value).strip().replace("\\", "/").rstrip("/")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="layout_check.py", description=__doc__)
    parser.add_argument("--root", default=".", help="project root (default: .)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    board_path = root / "board.json"
    try:
        board = json.loads(board_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"ERROR: board.json not found in {root}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"ERROR: board.json is invalid: {exc}", file=sys.stderr)
        return 2
    if not isinstance(board, dict):
        print("ERROR: board.json must be a JSON object", file=sys.stderr)
        return 2

    problems = []
    packages = board.get("packages") if isinstance(board.get("packages"), list) else []
    if board.get("profile") == "L" and not packages:
        problems.append("board.json: profile L needs packages[]")

    package_paths = [normalized(entry.get("path")) for entry in packages
                     if isinstance(entry, dict) and entry.get("path")]
    for entry in packages:
        if not isinstance(entry, dict):
            problems.append("board.json: package entry is not an object")
            continue
        path = normalized(entry.get("path"))
        if not path:
            problems.append("board.json: package entry has no path")
            continue
        folder = root / path
        if not folder.is_dir():
            problems.append(f"{path}: package folder is missing")
            continue
        if entry.get("kind") not in PACKAGE_KINDS:
            problems.append(f"{path}: kind {entry.get('kind')!r} is not one of {sorted(PACKAGE_KINDS)}")
        architecture = folder / "ARCHITECTURE.md"
        if not architecture.is_file():
            problems.append(f"{path}: ARCHITECTURE.md is missing")
        elif words(architecture) > BUDGETS["ARCHITECTURE.md"]:
            problems.append(f"{path}/ARCHITECTURE.md: {words(architecture)} words "
                            f"(max. {BUDGETS['ARCHITECTURE.md']})")
        agents = folder / "AGENTS.md"
        if agents.is_file() and words(agents) > BUDGETS["AGENTS.md"]:
            problems.append(f"{path}/AGENTS.md: {words(agents)} words (max. {BUDGETS['AGENTS.md']})")

    for entry in packages:
        if not isinstance(entry, dict) or not entry.get("path"):
            continue
        path = normalized(entry["path"])
        for imported in entry.get("may_import") or []:
            if not isinstance(imported, str):
                problems.append(f"{path}: may_import entry is not a string")
                continue
            if normalized(imported) not in package_paths:
                problems.append(f"{path}: may_import entry {imported!r} is not a declared package path")

    module_map = root / "docs/module-map.md"
    if not module_map.is_file():
        problems.append("docs/module-map.md is missing")
    else:
        text = module_map.read_text(encoding="utf-8")
        for path in package_paths:
            if path not in text:
                problems.append(f"docs/module-map.md: package {path} is not listed")

    contracts = board.get("contracts") if isinstance(board.get("contracts"), list) else []
    for contract in contracts:
        if not isinstance(contract, dict):
            problems.append("board.json: contract entry is not an object")
            continue
        name = contract.get("name", "?")
        path = normalized(contract.get("path"))
        if not path or not (root / path).exists():
            problems.append(f"contract {name}: path {contract.get('path')!r} does not exist")
        for schema_file in contract.get("schema_files") or []:
            if not (root / normalized(schema_file)).is_file():
                problems.append(f"contract {name}: schema file {schema_file!r} is missing")
        fixtures = contract.get("fixtures_dir")
        if not isinstance(fixtures, str) or not (root / normalized(fixtures)).is_dir():
            problems.append(f"contract {name}: fixtures_dir {fixtures!r} is missing")
        else:
            for side in ("valid", "invalid"):
                folder = root / normalized(fixtures) / side
                if not folder.is_dir() or not list(folder.glob("*.json")):
                    problems.append(f"contract {name}: no {side}/*.json fixture")

    tasks = board.get("tasks") if isinstance(board.get("tasks"), list) else []
    for task in tasks:
        if not isinstance(task, dict) or not task.get("package"):
            continue
        if normalized(task["package"]) not in package_paths:
            problems.append(f"{task.get('id', '?')}: package {task['package']!r} is not in packages[]")

    if problems:
        print(f"FAIL: {len(problems)} layout finding(s) in {root}")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print(f"OK: {board.get('project', root.name)}: {len(package_paths)} package(s), {len(contracts)} contract(s) agree with board.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
