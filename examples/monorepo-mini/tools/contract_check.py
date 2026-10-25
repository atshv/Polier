#!/usr/bin/env python3
"""Project gate: contract schema, version and fixtures agree.

Validates the fixtures of every contract in board.json against its JSON Schema
2020-12 subset: type, required, properties, items, additionalProperties, const,
enum, minimum, exclusiveMinimum and minLength. Unknown keywords are ignored.

Usage:
    python3 tools/contract_check.py
    python3 tools/contract_check.py --root /path/to/canvas-mini

Exit 0 = contracts ok, 1 = findings, 2 = configuration or usage error.
Standard library only; no network, no installs.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
JSON_SCHEMA_2020_12 = "https://json-schema.org/draft/2020-12/schema"
TYPE_CHECKS = {
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
    "string": lambda value: isinstance(value, str),
    "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "boolean": lambda value: isinstance(value, bool),
    "null": lambda value: value is None,
}


def normalized(value) -> str:
    return str(value).strip().replace("\\", "/").rstrip("/")


def resolve(schema: dict, root: dict):
    """Follow a local ``$ref`` of the form ``#/$defs/name``."""
    reference = schema.get("$ref")
    if not isinstance(reference, str):
        return schema
    if not reference.startswith("#/"):
        raise ValueError(f"unsupported $ref {reference!r}; only local references are supported")
    node = root
    for part in reference[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise ValueError(f"$ref {reference!r} does not resolve")
        node = node[part]
    return node


def validate(instance, schema, root: dict, path: str = "$") -> list:
    """Findings of `instance` against the supported subset of `schema`."""
    if not isinstance(schema, dict):
        return []
    schema = resolve(schema, root)
    findings: list = []

    expected = schema.get("type")
    if isinstance(expected, str) and expected in TYPE_CHECKS and not TYPE_CHECKS[expected](instance):
        return [f"{path}: expected {expected}, got {type(instance).__name__}"]

    if "const" in schema and instance != schema["const"]:
        findings.append(f"{path}: expected {schema['const']!r}, got {instance!r}")
    if isinstance(schema.get("enum"), list) and instance not in schema["enum"]:
        findings.append(f"{path}: {instance!r} is not one of {schema['enum']!r}")

    if isinstance(instance, dict):
        for name in schema.get("required") or []:
            if name not in instance:
                findings.append(f"{path}: missing required field {name!r}")
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        for name, subschema in properties.items():
            if name in instance:
                findings += validate(instance[name], subschema, root, f"{path}.{name}")
        additional = schema.get("additionalProperties", True)
        if additional is False:
            for name in instance:
                if name not in properties:
                    findings.append(f"{path}: unexpected field {name!r}")
        elif isinstance(additional, dict):
            for name in instance:
                if name not in properties:
                    findings += validate(instance[name], additional, root, f"{path}.{name}")
    elif isinstance(instance, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for index, item in enumerate(instance):
                findings += validate(item, items, root, f"{path}[{index}]")
    elif isinstance(instance, str) and isinstance(schema.get("minLength"), int):
        if len(instance) < schema["minLength"]:
            findings.append(f"{path}: shorter than minLength {schema['minLength']}")
    elif isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if isinstance(schema.get("minimum"), (int, float)) and instance < schema["minimum"]:
            findings.append(f"{path}: {instance} is below minimum {schema['minimum']}")
        if isinstance(schema.get("exclusiveMinimum"), (int, float)) \
                and instance <= schema["exclusiveMinimum"]:
            findings.append(f"{path}: {instance} must be greater than {schema['exclusiveMinimum']}")
    return findings


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="contract_check.py", description=__doc__)
    parser.add_argument("--root", default=".", help="project root (default: .)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    try:
        board = load_json(root / "board.json")
    except FileNotFoundError:
        print(f"ERROR: board.json not found in {root}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"ERROR: board.json is invalid: {exc}", file=sys.stderr)
        return 2

    contracts = board.get("contracts") if isinstance(board, dict) else None
    if not isinstance(contracts, list) or not contracts:
        print(f"OK: {root}: no contracts declared")
        return 0

    problems = []
    checked = 0
    for contract in contracts:
        if not isinstance(contract, dict):
            problems.append("board.json: contract entry is not an object")
            continue
        name = contract.get("name", "?")
        version = contract.get("version")
        if not isinstance(version, str) or not SEMVER.match(version):
            problems.append(f"contract {name}: version {version!r} is not SemVer")
            continue
        path = normalized(contract.get("path"))
        if not (root / path).is_dir():
            problems.append(f"contract {name}: path {path!r} does not exist")

        schemas = []
        for schema_file in contract.get("schema_files") or []:
            target = root / normalized(schema_file)
            try:
                schema = load_json(target)
            except (OSError, ValueError) as exc:
                problems.append(f"contract {name}: schema {schema_file!r} cannot be read: {exc}")
                continue
            if schema.get("$schema") != JSON_SCHEMA_2020_12:
                problems.append(f"contract {name}: schema {schema_file!r} is not JSON Schema 2020-12")
            schema_id = schema.get("$id")
            if not isinstance(schema_id, str) or f"/{version}/" not in schema_id:
                problems.append(f"contract {name}: $id {schema_id!r} does not contain version {version}")
            schemas.append((schema_file, schema))

        fixtures = normalized(contract.get("fixtures_dir"))
        if not (root / fixtures).is_dir():
            problems.append(f"contract {name}: fixtures_dir {fixtures!r} is missing")
            continue
        for schema_file, schema in schemas:
            for side, expect_valid in (("valid", True), ("invalid", False)):
                folder = root / fixtures / side
                files = sorted(folder.glob("*.json")) if folder.is_dir() else []
                if not files:
                    problems.append(f"contract {name}: no {side}/*.json fixture")
                    continue
                for fixture in files:
                    try:
                        data = load_json(fixture)
                    except (OSError, ValueError) as exc:
                        problems.append(f"{fixture.relative_to(root)}: cannot be read: {exc}")
                        continue
                    findings = validate(data, schema, schema)
                    checked += 1
                    if expect_valid and findings:
                        problems.append(f"{fixture.relative_to(root)}: valid fixture fails "
                                        + "; ".join(findings[:3]))
                    if not expect_valid and not findings:
                        problems.append(f"{fixture.relative_to(root)}: invalid fixture unexpectedly "
                                        f"validates against {schema_file!r}")

    if problems:
        print(f"FAIL: {len(problems)} contract finding(s) in {root}")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print(f"OK: {board.get('project', root.name)}: {len(contracts)} contract(s), {checked} fixture check(s) agree with the schema")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
