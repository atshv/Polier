# Architecture: canvas-mini

**As of:** 2026-10-17 · **Status:** binding · **Owner:** project team

## 1. Purpose and non-goals

A collaborative canvas editor: people place rectangles, ellipses and text on an infinite board and see each other's changes within a second. Version 1.0 is a web app whose document state is owned by a sync service and rendered by a C++ engine compiled to WebAssembly.

**Non-goals:** offline editing, file export/import, comments, version history UI, mobile apps, third-party plugins, a database.

## 2. Hard constraints

- C++17 scene core compiled with Emscripten; the browser is the only canvas runtime.
- TypeScript outside the engine; Node 22 for the service, the app and the build.
- Document state crosses package borders only as JSON that conforms to `contracts/state/state.schema.json` version 1.0.0.
- No database in 1.0: the sync service keeps the current document in memory and fans updates out to every connected client.
- Ports and test data come from the slot file `.polier-slot`, never from code.
- Code, comments, UI text and documents in English.

## 3. System shape and package kinds

```text
apps/web ──▶ packages/ui-kit ──▶ packages/engine (WASM)
    │                                   ▲
    └────────────▶ services/sync ───────┘
```

| Path | Kind | May import |
| --- | --- | --- |
| `packages/engine` | `package` | — |
| `packages/ui-kit` | `package` | `packages/engine` |
| `services/sync` | `service` | `packages/engine` |
| `apps/web` | `app` | `packages/engine`, `packages/ui-kit`, `services/sync` |

- The **engine** owns geometry, hit testing and the node model. It knows no DOM, no network and no storage.
- The **UI kit** owns presentation: components, design tokens, keyboard handling. It knows no transport.
- The **sync service** owns ordering and fan-out; it validates every document against the contract before broadcasting.
- The **app** owns composition and the transport client. It contains no geometry and no sync rules.

Details: `docs/module-map.md`, `docs/monorepo-layout.md`.

## 4. Invariants

| ID | Rule | Binds | Prevents |
| --- | --- | --- | --- |
| AD-1 | The state contract is the only data format shared across package borders; no package imports another package's internal files. | engine, ui-kit, sync, web | coupled rebuilds, silent field drift |
| AD-2 | Dependencies point one way: app → ui-kit → engine, app → service, service → engine. No package imports an app; the service imports no UI code. | all packages | cycles, browser code on the server |
| AD-3 | Document state is immutable per revision; every sync message carries the contract version and is rejected when the version does not match. | sync, web | half-applied updates, mixed client versions |
| AD-4 | The engine exposes only the C API declared in `packages/engine/include/engine/canvas.h`; WASM artifacts are build output and never committed. | engine, web | untraceable binaries, ABI drift |
| AD-5 | UI code uses the tokens of `packages/ui-kit/src/theme.css` only; no raw colour, spacing or duration values outside that file. | ui-kit, web | inconsistent UI, unmaintainable themes |
| AD-6 | Every environment has a smoke URL; a release is tagged on `main` only after the smoke gate passes. | operations | untested deploys |

## 5. Cross-package contracts

The single contract is `state` 1.0.0: a JSON Schema 2020-12 with one valid and one invalid fixture. Engine, UI kit, service and app consume the same version. A change is its own task with a version bump, refreshed fixtures and every dependant updated in the same task. Rules: `contracts/state/README.md`; decision: `docs/adr/ADR-0002-state-contract.md`.

## 6. Quality gates

- `layout` — `python3 tools/layout_check.py`: board package map, folders and contract files agree.
- `contracts` — `python3 tools/contract_check.py`: schema version, fixtures and required fields.
- `configure`, `build`, `cpp-unit` — CMake and CTest in `packages/engine`.
- `wasm-build`, `wasm-test`, `wasm-size` — Emscripten build and its size budget.
- `types`, `tests`, `lint` — TypeScript in each package.
- `boundaries` — `.generator/tools/boundaries.py` against `packages[].may_import`.
- `e2e` (exclusive) — Playwright against the slot ports; `smoke` — post-deploy check; `release` — release check.

Command shapes per stack: `docs/gates/`. Gate definitions: `docs/quality.md`.

## 7. Open / deferred

- Local-first editing and conflict resolution: after stage 2.
- Presence cursors and comments: after 1.0.
- Engine spike decision: the owner reviews the size budget of `ENG-02` and records continue/stop for the stage (`docs/releasing.md`).

## 8. References

- Module structure: `docs/module-map.md`
- Layout and budgets: `docs/monorepo-layout.md`
- Quality and gates: `docs/quality.md`
- Dependency versions: `docs/versions.md`
- Decisions: `docs/adr/ADR-0001-monorepo.md`, `docs/adr/ADR-0002-state-contract.md`
