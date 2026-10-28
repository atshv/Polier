# Status

**Project:** canvas-mini · **Profile:** L · **Stage:** 1 of 4 (4 defined)

> Generated from `board.json`. Do not edit by hand.

## Stages

### Stage 1 — `foundation` Foundation

- State: complete
- Owner decision: `continue`
- Exit gates: `layout`, `contracts`
- Exit criteria: All four package folders exist with their ARCHITECTURE.md and stay inside the package word budget.; The state contract has a schema, one valid and one invalid fixture and version 1.0.0 on the board.; The layout and contract gates pass with records in reviews/evidence.
- Tasks: F-01, F-02

### Stage 2 — `engine-spike` Engine spike

- State: waiting for the owner decision
- Owner decision: `pending`
- Exit gates: `cpp-unit` (missing record), `wasm-build` (missing record)
- Exit criteria: The C++ unit suite is green.; The WebAssembly module builds and its size is within the documented budget.; The owner records continue or stop for the stage after the size review.
- Tasks: ENG-01, ENG-02
- Tasks open: ENG-01, ENG-02

### Stage 3 — `surface` Surface

- State: exit gates missing: types, tests, boundaries
- Owner decision: `continue`
- Exit gates: `types` (missing record), `tests` (missing record), `boundaries` (missing record)
- Exit criteria: The service validates and serves the contract version on its slot port.; The UI kit renders the stage and the toolbar from design tokens with component tests.; Both packages pass types, tests and boundaries.
- Tasks: API-01, WEB-01
- Tasks open: API-01, WEB-01

### Stage 4 — `web` Web app and release

- State: waiting for the owner decision
- Owner decision: `pending`
- Exit gates: `e2e` (missing record), `smoke` (missing record), `release` (missing record)
- Exit criteria: The e2e flow passes against the slot ports and the smoke check passes on every environment.; The release check passes on a tagged main.; CHANGELOG.md describes the release and every dependency is pinned.
- Tasks: WEB-02, REL-01
- Tasks open: WEB-02, REL-01

## Packages

- `packages/engine` — kind: `package` — may import: —
- `packages/ui-kit` — kind: `package` — may import: packages/engine
- `services/sync` — kind: `service` — may import: packages/engine
- `apps/web` — kind: `app` — may import: packages/engine, packages/ui-kit, services/sync

## Runtime

- Slots: 3 (0 = main checkout) · ports: 4100 + 50·N
- Services: web +0, api +1
- Ports, database and bucket names: read `.polier-slot` (`tools/slot.py show`)

## Ready now

- `ENG-01` C++ scene core and unit tests
  - F-01: Workspace folders: packages/engine, packages/ui-kit, services/sync, apps/web; package map in docs/module-map.md.
  - F-01: Scaffold gate: python3 tools/layout_check.py fails when a packages[].path or its ARCHITECTURE.md is missing.
  - F-02: State contract 1.0.0 lives in contracts/state; consumers mirror it in services/sync/src/state.ts and packages/ui-kit/src/index.ts.
  - F-02: Change the contract in its own task: bump board.json and the schema $id together, then run python3 tools/contract_check.py.

## Orchestration

- Limits: 3 attempts/task, 3 in progress
- Next wave: `ENG-01` (tasks/ENG-01.md)
- Running: none
- Blocked: ENG-02 (open dependency); API-01, WEB-01, WEB-02, REL-01 (stage waits)
- Approvals pending: `AP-001` new_dependency for API-01

## Done

- [x] `F-01` Workspace scaffold and package map — status: `done` — owner: worker-1
- [x] `F-02` State contract schema and fixtures — status: `done` — owner: worker-1

## In progress

- none

## Blocked / failed

- none

## Open

- [ ] `ENG-01` C++ scene core and unit tests — status: `pending` — owner: —
- [ ] `ENG-02` WASM bindings and size budget — status: `pending` — owner: —
- [ ] `API-01` Sync service over the state contract — status: `pending` — owner: —
- [ ] `WEB-01` Toolbar and stage in the UI kit — status: `pending` — owner: —
- [ ] `WEB-02` Web app shell and sync wiring — status: `pending` — owner: —
- [ ] `REL-01` Release readiness and environments — status: `pending` — owner: —

## Decisions

- 2026-10-17 `ADR-0001` Monorepo with four workspace packages (`docs/adr/ADR-0001-monorepo.md`)
- 2026-10-17 `ADR-0002` The state contract is JSON Schema 2020-12 (`docs/adr/ADR-0002-state-contract.md`)

## Open questions

- `Q1` Does the 1.0 release need offline editing before the engine spike ends? — blocks: WEB-02 — status: `open`
