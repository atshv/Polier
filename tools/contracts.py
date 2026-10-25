#!/usr/bin/env python3
"""Machine-readable contracts with version rules (PL-12).

A contract on ``board.json`` looks like::

    {"name": "sync-events", "path": "contracts/sync", "version": "1.2.0",
     "schema_files": ["contracts/sync/schema.json"],
     "fixtures_dir": "contracts/sync/fixtures",
     "dependants": ["services/sync", "apps/web/src/api.ts"]}

``contract_errors`` checks that the files and fixtures exist, that the version
was bumped when files changed since the base branch (SemVer: major for removed
or renamed schema properties, minor for added optional ones, otherwise at
least patch) and that the running task's ``scope_write`` covers every
dependant (or lists it in ``contract_followups`` for a lead-approved follow-up).

Usage:
    python3 tools/contracts.py check [--root PATH] [--base BRANCH]
                                     [--task ID] [--json]
    python3 tools/contracts.py list  [--root PATH] [--json]

Exit codes: 0 clean, 1 findings, 2 configuration or usage error.
Standard library only; JSON Schema is treated as plain JSON.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.board import load_board  # noqa: E402
from core.errors import PolierError  # noqa: E402

SEMVER = re.compile(r"^([0-9]+)\.([0-9]+)\.([0-9]+)$")
BUMPS = {"patch": 0, "minor": 1, "major": 2}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _norm(value) -> str:
    value = str(value).strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value.rstrip("/")


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _parse_semver(value) -> Optional[Tuple[int, int, int]]:
    if not isinstance(value, str):
        return None
    match = SEMVER.match(value.strip())
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _higher_bump(left: str, right: str) -> str:
    return left if BUMPS.get(left, 0) >= BUMPS.get(right, 0) else right


def _covered(path: str, scopes: List[str]) -> bool:
    """True when one scope entry covers `path` (same path or either side of it)."""
    target = _norm(path)
    for scope in scopes:
        scope = _norm(scope)
        if not scope:
            continue
        if target == scope or target.startswith(scope + "/") or scope.startswith(target + "/"):
            return True
    return False


# ---------------------------------------------------------------------------
# JSON-Schema property diff
# ---------------------------------------------------------------------------

def _properties(schema) -> List[Tuple[str, object]]:
    """Every property path in a JSON Schema with its subschema, in a stable order."""
    found: List[Tuple[str, object]] = []
    seen: Set[str] = set()

    def add(prefix: str, name: str, subschema) -> str:
        path = f"{prefix}.{name}" if prefix else str(name)
        if path not in seen:
            seen.add(path)
            found.append((path, subschema))
        return path

    def walk(node, prefix: str) -> None:
        if not isinstance(node, dict):
            return
        properties = node.get("properties")
        if isinstance(properties, dict):
            for name in sorted(properties):
                path = add(prefix, name, properties[name])
                walk(properties[name], path)
        items = node.get("items")
        if isinstance(items, dict):
            walk(items, prefix)
        elif isinstance(items, list):
            for entry in items:
                walk(entry, prefix)
        additional = node.get("additionalProperties")
        if isinstance(additional, dict):
            walk(additional, prefix)
        for key in ("$defs", "definitions"):
            block = node.get(key)
            if isinstance(block, dict):
                for name in sorted(block):
                    walk(block[name], f"{prefix}.{name}" if prefix else str(name))
        for key in ("allOf", "anyOf", "oneOf"):
            block = node.get(key)
            if isinstance(block, list):
                for entry in block:
                    walk(entry, prefix)

    walk(schema, "")
    return found


def _required_paths(schema) -> Set[str]:
    """Property paths that a schema marks as required, including nested ones."""
    required: Set[str] = set()

    def walk(node, prefix: str) -> None:
        if not isinstance(node, dict):
            return
        names = node.get("required")
        if isinstance(names, list):
            for name in names:
                if isinstance(name, str):
                    required.add(f"{prefix}.{name}" if prefix else name)
        properties = node.get("properties")
        if isinstance(properties, dict):
            for name in sorted(properties):
                walk(properties[name], f"{prefix}.{name}" if prefix else str(name))
        items = node.get("items")
        if isinstance(items, dict):
            walk(items, prefix)
        elif isinstance(items, list):
            for entry in items:
                walk(entry, prefix)
        additional = node.get("additionalProperties")
        if isinstance(additional, dict):
            walk(additional, prefix)
        for key in ("$defs", "definitions"):
            block = node.get(key)
            if isinstance(block, dict):
                for name in sorted(block):
                    walk(block[name], f"{prefix}.{name}" if prefix else str(name))
        for key in ("allOf", "anyOf", "oneOf"):
            block = node.get(key)
            if isinstance(block, list):
                for entry in block:
                    walk(entry, prefix)

    walk(schema, "")
    return required


def compare_schemas(old, new) -> dict:
    """Added, removed and renamed properties between two parsed JSON Schemas.

    A removed property and an added property with the same subschema count as
    one rename (``"old.path -> new.path"``). Paths are dotted property names,
    e.g. ``"event.userName"``. Plain JSON, no ``jsonschema`` dependency.
    """
    old_properties = dict(_properties(old))
    new_properties = dict(_properties(new))
    removed_paths = sorted(set(old_properties) - set(new_properties))
    added_paths = sorted(set(new_properties) - set(old_properties))

    renamed: List[str] = []
    removed: List[str] = []
    unmatched_added = list(added_paths)
    for old_path in removed_paths:
        match = None
        for new_path in unmatched_added:
            if _canonical(old_properties[old_path]) == _canonical(new_properties[new_path]):
                match = new_path
                break
        if match is None:
            removed.append(old_path)
        else:
            unmatched_added.remove(match)
            renamed.append(f"{old_path} -> {match}")
    return {"added": unmatched_added, "removed": removed, "renamed": renamed}


def required_change(kind, old_version, new_version) -> Optional[str]:
    """The error message when `new_version` lacks the bump `kind` needs, else None.

    `kind` is the minimum SemVer bump the change requires: ``"major"``,
    ``"minor"`` or ``"patch"``. `old_version` None (a new contract) never fails.
    """
    if kind not in BUMPS:
        return None
    if old_version is None:
        return None
    old = _parse_semver(old_version)
    new = _parse_semver(new_version)
    if old is None or new is None:
        return f"{kind} required (version {new_version!r} is not SemVer, expected e.g. 1.0.0)"
    if kind == "patch":
        ok = new > old
    elif kind == "minor":
        ok = new[0] > old[0] or (new[0] == old[0] and new[1] > old[1])
    else:
        ok = new[0] > old[0]
    return None if ok else f"{kind} required"


# ---------------------------------------------------------------------------
# git
# ---------------------------------------------------------------------------

class _Git:
    """Thin, non-raising git wrapper for one project root."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._repo: Optional[bool] = None
        self._prefix: Optional[str] = None

    def run(self, *args: str) -> Tuple[bool, str, str]:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.root), *args],
                capture_output=True, text=True, check=False,
            )
        except (FileNotFoundError, OSError) as exc:
            return False, "", str(exc)
        return result.returncode == 0, result.stdout, result.stderr.strip()

    @property
    def available(self) -> bool:
        if self._repo is None:
            ok, out, _ = self.run("rev-parse", "--is-inside-work-tree")
            self._repo = ok and out.strip() == "true"
        return bool(self._repo)

    @property
    def prefix(self) -> str:
        """The project root relative to the git top level, e.g. ``examples/app/``."""
        if self._prefix is None:
            ok, out, _ = self.run("rev-parse", "--show-prefix")
            self._prefix = out.strip() if ok else ""
        return self._prefix

    def show(self, revision: str, rel_path: str) -> Optional[str]:
        # <rev>:<path> is relative to the repository top level, not to the root.
        ok, out, _ = self.run("show", f"{revision}:{self.prefix}{_norm(rel_path)}")
        return out if ok else None

    def changed_paths(self, base: str, paths: List[str]) -> Tuple[bool, Set[str]]:
        """(comparable, changed files) of `paths` since `base`.

        Committed changes use ``git diff base...HEAD``; when that fails the
        two-dot form ``git diff base`` is the fallback. Uncommitted and
        untracked files count as changed as well.
        """
        if not paths:
            return True, set()
        changed: Set[str] = set()
        ok, out, _ = self.run("diff", "--name-only", f"{base}...HEAD", "--", *paths)
        if ok:
            changed.update(line.strip() for line in out.splitlines() if line.strip())
        else:
            ok, out, _ = self.run("diff", "--name-only", base, "--", *paths)
            if not ok:
                return False, set()
            changed.update(line.strip() for line in out.splitlines() if line.strip())
        ok, out, _ = self.run("diff", "--name-only", "HEAD", "--", *paths)
        if ok:
            changed.update(line.strip() for line in out.splitlines() if line.strip())
        ok, out, _ = self.run("ls-files", "--others", "--exclude-standard", "--", *paths)
        if ok:
            changed.update(line.strip() for line in out.splitlines() if line.strip())
        return True, changed


def _base_board(git: _Git, base: str, warn) -> Optional[dict]:
    text = git.show(base, "board.json")
    if text is None:
        warn(f"contracts: cannot read board.json on {base}; version rules are skipped")
        return None
    try:
        data = json.loads(text)
    except ValueError as exc:
        warn(f"contracts: board.json on {base} is not valid JSON ({exc}); version rules are skipped")
        return None
    return data if isinstance(data, dict) else None


def _contract_named(board: Optional[dict], name: str) -> Optional[dict]:
    if not isinstance(board, dict):
        return None
    contracts = board.get("contracts")
    if not isinstance(contracts, list):
        return None
    for contract in contracts:
        if isinstance(contract, dict) and contract.get("name") == name:
            return contract
    return None


def _schema_kind(git: _Git, base: str, parsed: Dict[str, object], warn) -> Tuple[str, str]:
    """Minimum bump and a human reason for the schema changes since `base`."""
    kind = "patch"
    details: List[str] = []
    for rel in sorted(parsed):
        old_text = git.show(base, rel)
        if old_text is None:
            details.append(f"new schema {rel}")
            kind = _higher_bump(kind, "minor")
            continue
        try:
            old_schema = json.loads(old_text)
        except ValueError:
            warn(f"contracts: schema {rel} on {base} is not valid JSON; its diff is skipped")
            continue
        new_schema = parsed[rel]
        changes = compare_schemas(old_schema, new_schema)
        if changes["renamed"]:
            details.append("renamed property " + ", ".join(changes["renamed"]))
            kind = _higher_bump(kind, "major")
        if changes["removed"]:
            details.append("removed property " + ", ".join(changes["removed"]))
            kind = _higher_bump(kind, "major")
        if changes["added"]:
            required = _required_paths(new_schema)
            required_added = [path for path in changes["added"] if path in required]
            if required_added:
                details.append("added required property " + ", ".join(required_added))
                kind = _higher_bump(kind, "major")
            else:
                details.append("added property " + ", ".join(changes["added"]))
                kind = _higher_bump(kind, "minor")
        if not changes["added"] and not changes["removed"] and not changes["renamed"]:
            if _canonical(old_schema) != _canonical(new_schema):
                details.append(f"changed schema {rel}")
                kind = _higher_bump(kind, "patch")
    if not details:
        details.append("files changed")
    return kind, "; ".join(details)


# ---------------------------------------------------------------------------
# the check
# ---------------------------------------------------------------------------

def _select_tasks(board: dict, task: Optional[str]) -> Tuple[List[dict], Optional[str]]:
    tasks = [entry for entry in (board.get("tasks") or []) if isinstance(entry, dict)]
    if task:
        for entry in tasks:
            if entry.get("id") == task:
                return [entry], None
        return [], f"task {task!r} is not on the board"
    return [entry for entry in tasks if entry.get("status") == "in_progress"], None


def contract_errors(root, board, base_branch=None, task=None) -> Tuple[List[str], List[str]]:
    """Contract findings of a project as ``(errors, warnings)``.

    Pure checker used by ``tools/contracts.py`` and ``tools/check.py``: it never
    exits and never writes. `base_branch` overrides ``board.json`` -> base_branch;
    `task` selects the running task for the dependant check instead of the
    tasks that are ``in_progress`` on the board.
    """
    errors: List[str] = []
    warnings: List[str] = []
    seen_warnings: Set[str] = set()

    def warn(message: str) -> None:
        if message not in seen_warnings:
            seen_warnings.add(message)
            warnings.append(message)

    root = Path(os.path.abspath(str(root)))
    if not isinstance(board, dict):
        return errors, warnings
    contracts = board.get("contracts")
    if contracts is None:
        return errors, warnings
    if not isinstance(contracts, list):
        errors.append("board.json: contracts must be an array")
        return errors, warnings
    if not contracts:
        return errors, warnings

    base = base_branch if isinstance(base_branch, str) and base_branch.strip() else board.get("base_branch")
    base = base.strip() if isinstance(base, str) else ""
    git = _Git(root)
    if not git.available:
        warn(f"contracts: no git repository at {root}; version rules and dependant diffs are skipped")
        base = ""
    elif not base:
        warn("contracts: board.json has no base_branch; version rules are skipped")

    base_board = _base_board(git, base, warn) if git.available and base else None
    running_tasks, task_problem = _select_tasks(board, task)
    if task_problem:
        errors.append(task_problem)
        running_tasks = []

    for index, contract in enumerate(contracts):
        if not isinstance(contract, dict):
            errors.append(f"board.json: contract {index + 1} is not an object")
            continue
        name = contract.get("name")
        if not isinstance(name, str) or not name.strip():
            name = f"contract {index + 1}"
        label = f"contract {name}"
        version = contract.get("version")

        # Files and fixtures.
        raw_path = contract.get("path")
        path: Optional[str] = None
        if not isinstance(raw_path, str) or not raw_path.strip():
            errors.append(f"{label}: path is missing or is not a string")
        else:
            path = _norm(raw_path)
            if not (root / path).exists():
                errors.append(f"{label}: path {raw_path!r} does not exist")

        raw_schemas = contract.get("schema_files")
        schema_files = [entry for entry in raw_schemas if isinstance(entry, str)] \
            if isinstance(raw_schemas, list) else []
        if isinstance(raw_schemas, list) and not raw_schemas:
            warn(f"{label}: no schema_files declared; only version and fixtures are checked")
        parsed_schemas: Dict[str, object] = {}
        for schema_file in schema_files:
            rel = _norm(schema_file)
            target = root / rel
            if not target.is_file():
                errors.append(f"{label}: schema file {schema_file!r} does not exist")
                continue
            try:
                parsed_schemas[rel] = json.loads(target.read_text(encoding="utf-8"))
            except (ValueError, OSError) as exc:
                errors.append(f"{label}: schema file {schema_file!r} is not valid JSON: {exc}")

        raw_fixtures = contract.get("fixtures_dir")
        if not isinstance(raw_fixtures, str) or not raw_fixtures.strip():
            errors.append(f"{label}: fixtures_dir is missing or is not a string")
        else:
            fixtures = root / _norm(raw_fixtures)
            if not fixtures.is_dir():
                errors.append(f"{label}: fixtures_dir {raw_fixtures!r} does not exist "
                              f"(needs valid/*.json and invalid/*.json)")
            else:
                for side in ("valid", "invalid"):
                    folder = fixtures / side
                    files = sorted(folder.glob("*.json")) if folder.is_dir() else []
                    if not files:
                        errors.append(
                            f"{label}: fixtures_dir {raw_fixtures!r} has no {side}/*.json fixture "
                            f"(needs at least one valid and one invalid fixture)")

        # Version rules and dependants.
        changed_files: Set[str] = set()
        changed = False
        if git.available and base:
            diff_paths: List[str] = []
            if path is not None and (root / path).exists():
                diff_paths.append(path)
            diff_paths.extend(sorted(parsed_schemas))
            comparable, changed_files = git.changed_paths(base, diff_paths)
            if not comparable:
                warn(f"contracts: cannot compare with base branch {base!r} "
                     f"(unknown revision or not a repository); version rules are skipped")
                changed_files = set()
            changed = bool(changed_files)
        if changed:
            base_contract = _contract_named(base_board, name)
            base_version = base_contract.get("version") if base_contract else None
            if base_contract is None:
                if base_board is not None:
                    warn(f"{label}: new since {base}; no version bump to compare")
            else:
                kind, detail = _schema_kind(git, base, parsed_schemas, warn)
                verdict = required_change(kind, base_version, version)
                if verdict:
                    errors.append(
                        f"{label}: {detail} since {base}, version {base_version!r} -> "
                        f"{version!r}: {verdict} (bump the version)")
        if changed:
            dependants = [entry for entry in contract.get("dependants") or []
                          if isinstance(entry, str) and entry.strip()]
            if dependants and not running_tasks:
                if task is None:
                    warn(f"{label}: changed, but no task is in_progress; dependant check skipped")
                continue
            for running in running_tasks:
                scope = [_norm(entry) for entry in running.get("scope_write") or []
                         if isinstance(entry, str)]
                followups = [_norm(entry) for entry in running.get("contract_followups") or []
                             if isinstance(entry, str)]
                for dependant in dependants:
                    if _covered(dependant, scope):
                        continue
                    if _covered(dependant, followups):
                        warn(f"{label}: task {running.get('id')} leaves dependant {dependant} "
                             f"out of scope_write but lists it in contract_followups "
                             f"(lead approval required)")
                    else:
                        errors.append(
                            f"{label}: changed since {base or 'the base branch'}, but task "
                            f"{running.get('id')} scope_write does not include dependant "
                            f"{dependant} (add it or list it in contract_followups)")
    return errors, warnings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _summaries(board: dict) -> List[dict]:
    out = []
    for contract in board.get("contracts") or []:
        if isinstance(contract, dict):
            out.append({
                "name": contract.get("name"),
                "version": contract.get("version"),
                "path": contract.get("path"),
            })
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="contracts.py",
        description="Machine-readable contracts with version rules.",
    )
    subparsers = parser.add_subparsers(dest="command")
    check = subparsers.add_parser("check", help="check contracts, versions and dependants")
    check.add_argument("--root", default=".", help="project root (default: .)")
    check.add_argument("--base", default=None, help="base branch (default: board base_branch)")
    check.add_argument("--task", default=None, help="task ID for the dependant check")
    check.add_argument("--json", action="store_true", help="print the result as JSON")
    list_cmd = subparsers.add_parser("list", help="list the contracts and their versions")
    list_cmd.add_argument("--root", default=".", help="project root (default: .)")
    list_cmd.add_argument("--json", action="store_true", help="print the contract list as JSON")
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help(sys.stderr)
        return 2

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"ERROR: project root not found: {root}", file=sys.stderr)
        return 2
    try:
        board = load_board(root)
    except PolierError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.command == "list":
        contracts = _summaries(board)
        if args.json:
            print(json.dumps(contracts, indent=2, ensure_ascii=False))
        elif not contracts:
            print(f"No contracts declared on {root / 'board.json'}.")
        else:
            for entry in contracts:
                print(f"{entry['name']}  {entry['version']}  {entry['path']}")
        return 0

    if args.task:
        known = {entry.get("id") for entry in board.get("tasks") or [] if isinstance(entry, dict)}
        if args.task not in known:
            print(f"ERROR: task {args.task!r} is not on the board", file=sys.stderr)
            return 2

    errors, warnings = contract_errors(
        root, board, base_branch=args.base, task=args.task)
    result = {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "contracts": _summaries(board),
    }
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        for warning in warnings:
            print(f"WARN: {warning}")
        if errors:
            print(f"FAIL: {len(errors)} contract finding(s) in {root}\n")
            for error in errors:
                print(f"- {error}")
        else:
            suffix = f" ({len(warnings)} warning(s))" if warnings else ""
            print(f"OK: contracts pass in {root}{suffix}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
