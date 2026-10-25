# ADR-0002 — The state contract is JSON Schema 2020-12

**Status:** accepted · **Date:** 2026-10-17 · **Deciders:** project team

## Context

Engine, UI kit, sync service and app exchange the document state. A shared TypeScript type would only reach the TypeScript packages; the C++ engine cannot consume it. The team wants one versioned description that every stack can read and validate, with fixtures that show a valid and an invalid document.

## Decision

The document state is described by one JSON Schema 2020-12 file, `contracts/state/state.schema.json`, version 1.0.0:

- `$id` carries the contract name and the version; the schema and `board.json` change their version together.
- `contracts/state/fixtures/valid/state.json` must validate; `contracts/state/fixtures/invalid/state.json` must not. Validating fixtures is a project gate (`tools/contract_check.py`); the Polier copy only checks presence and versioning.
- Field removed or renamed → major bump. Required field added → major bump. Optional field added → minor. Documentation or format fix → patch.
- Every dependant (`packages/engine/include/engine`, `packages/ui-kit/src`, `services/sync/src`, `apps/web/src`) changes in the same task, or the task lists a lead-approved `contract_followups` entry.

## Consequences

- The engine validates the same document the browser sends; a version mismatch is rejected at the service border.
- Contract changes are visible in review: schema diff, fixture change and version bump in one diff.
- Cost: JSON is validated per message, so the service keeps the validator small and allocation-free in the hot path.

## Alternatives

- Protobuf: compact and typed in C++ and TypeScript, but adds a compiler step and a second schema language to the toolchain.
- Shared TypeScript types: no dependency, but the engine and the service cannot use them, so the two sides would drift.
