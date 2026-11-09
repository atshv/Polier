# Contract: state

**Version:** `1.0.0` · **Status:** active · **Owner:** project team · **Board entry:** `contracts[]` → `state`

## Purpose

The document state exchanged between the engine, the UI kit, the sync service and the web app. The schema is binding; this file explains intent and the change rules.

## Schema and fixtures

- **Schema:** [`state.schema.json`](state.schema.json), JSON Schema 2020-12; `$id` carries the contract name and the version.
- **Valid fixture:** [`fixtures/valid/state.json`](fixtures/valid/state.json) — must validate.
- **Invalid fixture:** [`fixtures/invalid/state.json`](fixtures/invalid/state.json) — must not validate (wrong contract version, empty document id, negative width, zero zoom).
- **Dependants:** `packages/engine/include/engine`, `packages/ui-kit/src`, `services/sync/src`, `apps/web/src`. They consume this schema, never each other's internals.
- **Gate:** `python3 tools/contract_check.py` → exit 0.

## Version rules

| Change | Bump |
| --- | --- |
| field removed or renamed | major |
| required field or behaviour added | major |
| optional field added | minor |
| docs or format fix, no behaviour change | patch |

- Bump the version in `board.json`, in the schema `$id` and in the schema's `version` const in the same task as the change.
- Review every dependant in that task; if one cannot follow immediately, list it in `contract_followups` and get the lead's approval.
- A consumer may follow a newer optional field only after the contract version is active.

## Change procedure

1. Change the schema and add a fixture for the new valid and invalid case.
2. Bump the version (table above) and update `board.json`.
3. Update every dependant; run its gates.
4. Record the decision in the task result and, for a major bump, in `docs/adr/`.
