# Contract: <name>

> Profile L: copy to `docs/contracts/<name>.md` and complete the `contracts[]` entry in `board.json`. Delete it if the packages share no interface.

**Version:** `<x.y.z>` · **Status:** `<draft | active | deprecated>` · **Owner:** <role> · **Board entry:** `contracts[]` → `<name>`

## Purpose

<What does this interface guarantee, and which packages depend on it? The schema is binding; this file explains intent and the change rules.>

## Schema and fixtures

- **Schema:** `schema_files[]` from `board.json`, JSON Schema 2020-12, `$id` contains name and version.
- **Fixtures:** `fixtures_dir` from `board.json` — at least one valid and one invalid case.
- **Dependants:** `packages[]` paths and files listed under `dependants` on the board; they consume the contract, never each other's internals.
- **Gate:** `python3 <package>/tools/contracts.py check` → exit 0.

## Version rules

| Change | Bump |
| --- | --- |
| field removed or renamed | major |
| required field or behaviour added | major |
| optional field added | minor |
| docs or format fix, no behaviour change | patch |

- Bump the version in `board.json` and in the schema `$id` in the same task as the change.
- Review every dependant file in that task; if one cannot follow immediately, list it in `contract_followups` and get the lead's approval.
- A consumer may follow a newer optional field only after the contract version is active.

## Change procedure

1. Change the schema and add a fixture for the new valid and invalid case.
2. Bump the version (table above) and update `board.json`.
3. Update every dependant; run its gates.
4. Record the decision in the task result and, for a major bump, in `docs/adr/`.
