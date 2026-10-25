# Module Structure: canvas-mini

> Detail document for `ARCHITECTURE.md`. Package map and import rules, no architecture decisions.

## Package map (profile L)

| Package path | Kind | Owner | May import | Build / test |
|---|---|---|---|---|
| `packages/engine/` | `package` | geometry owner | — | `cmake -S packages/engine -B packages/engine/build && cmake --build packages/engine/build`, `ctest --test-dir packages/engine/build --output-on-failure` |
| `packages/ui-kit/` | `package` | UI owner | `packages/engine/` | `npm run build`, `npm test` |
| `services/sync/` | `service` | sync owner | `packages/engine/` | `npm run build`, `npm test` |
| `apps/web/` | `app` | app owner | `packages/engine/`, `packages/ui-kit/`, `services/sync/` | `npm run build`, `npm run e2e` |

Every row is a `packages[]` entry in `board.json`. The `boundaries` gate compares the imports of the sources with the `may_import` column and reports file, line and package on a violation.

## Layers inside a package

Dependencies only point one way: UI → logic → data. The package border is stronger than the layer border: a package never imports another package's internal files, only its public entry point or the contract.

| Layer | Where | Purpose | May import | May not import |
|---|---|---|---|---|
| UI | `packages/ui-kit/src/components/`, `apps/web/src/app/` | presentation, input, design tokens | logic, UI components | data clients, raw JSON |
| Logic | `packages/engine/src/`, `services/sync/src/state.ts` | geometry, validation rules, domain types | data, own domain types | UI components |
| Data | `services/sync/src/server.ts`, `apps/web/src/lib/sync-client.ts`, `contracts/state/` | transport, schemas, storage adapters | standard library, contract | UI, logic rules |

## Contract boundary

`contracts/state/` is the only shared representation: a JSON Schema 2020-12 plus a valid and an invalid fixture, version 1.0.0. `packages/engine/include/engine/`, `packages/ui-kit/`, `services/sync/` and `apps/web/` are its dependants. The schema is binding; the README explains the version rules.

## Support scripts

| Path | Purpose | Command |
|---|---|---|
| `tools/layout_check.py` | board packages, folders and contract files agree | `python3 tools/layout_check.py` |
| `tools/contract_check.py` | schema version, fixtures and required fields match | `python3 tools/contract_check.py` |
| `.generator/tools/` | Polier gates, slot, smoke and release helpers (gitignored) | `python3 .generator/tools/gate.py --help` |

## Dependency rules

1. Dependencies point one way: app → UI kit → engine, app → service, service → engine. No cycles.
2. No package imports an app; the sync service imports no UI code and no browser globals.
3. Cross-package types come from the state contract, not from another package's source file.
4. New files go into their package and layer; no file "somewhere" in the repository root.
5. A task changes one package if possible; a contract change touches schema, fixtures and every dependant.
6. The table is binding; deviations need an ADR.

## Folder map

```text
packages/engine/       C++ core: include/, src/, types/, tests/ (ENG-01)
packages/ui-kit/       components/, theme.css, tests/ (WEB-01)
services/sync/         server.ts, state.ts, index.ts, tests/ (API-01)
apps/web/              src/app/, src/lib/, tests/e2e/ (WEB-02)
contracts/state/       schema, fixtures, README (F-02)
tools/                 project gate scripts
docs/                  module map, quality, versions, environments, releasing, gates, ADRs
tasks/                 one brief per task
reviews/evidence/      gate records written by the Polier gate runner
```
