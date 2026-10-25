# Monorepo Layout: canvas-mini

> Detail document for `ARCHITECTURE.md` at profile L. Root files stay small; each package carries its own context.

## Root files

- `ARCHITECTURE.md` — system shape, package kinds, dependency direction, invariants (max. 800 words).
- `AGENTS.md` — root commands and rules only (max. 400 words).
- `docs/module-map.md` — package map: path, kind, owner, may_import, build/test commands.
- `docs/monorepo-layout.md` — this file.
- `docs/quality.md`, `docs/versions.md`, `docs/environments.md`, `docs/releasing.md`, `docs/design-rules.md`.
- Briefs list root files plus the files of their own package only.

## Package files

Each package gets:

- `<package>/ARCHITECTURE.md` (max. 400 words): purpose, inputs, outputs, invariants, allowed imports, build/test commands.
- `<package>/AGENTS.md` (optional, max. 200 words): commands and pitfalls that differ from the root file.

The engine and the sync service carry an `AGENTS.md`; the UI kit and the app use the root commands unchanged.

## Dependency direction

| Package | Kind | May import | Never imports |
|---|---|---|---|
| `packages/engine` | package | — | any other package |
| `packages/ui-kit` | package | `packages/engine` | services, apps |
| `services/sync` | service | `packages/engine` | apps, UI components |
| `apps/web` | app | `packages/engine`, `packages/ui-kit`, `services/sync` | package internals |

- The gate is `python3 .generator/tools/boundaries.py .`; it reads `packages[].may_import` and names file, line and package on a violation.
- No cycles: a cycle means merge the packages or move the shared part into the state contract.
- Cross-package interfaces live in `contracts/` and are versioned. A contract change updates every dependant in the same task or lists a lead-approved entry in `contract_followups`.

## Ownership and writes

- One writer per package per stage. A task with `package` writes inside that package; contract paths from `board.json` are the only exception.
- Two packages may be built in parallel only with disjoint `scope_write` and no shared decision. `API-01` (service) and `WEB-01` (UI kit) form such a pair in stage `surface`.
- Stage 1 writes per-package files only for the packages it creates: all four exist after `F-01`, so all four carry `ARCHITECTURE.md` from the start.

## Folder tree

```text
├── ARCHITECTURE.md
├── AGENTS.md
├── board.json
├── docs/
│   ├── module-map.md
│   ├── monorepo-layout.md
│   ├── quality.md
│   ├── versions.md
│   ├── environments.md
│   ├── releasing.md
│   ├── design-rules.md
│   ├── adr/
│   └── gates/
├── contracts/state/
├── packages/
│   ├── engine/
│   └── ui-kit/
├── services/sync/
├── apps/web/
├── tools/
├── tasks/
└── reviews/evidence/
```

## Budgets

| File | Profile L limit | Current target |
|---|---|---|
| `ARCHITECTURE.md` | 800 words | 600–750 |
| `AGENTS.md` | 400 words | 300–380 |
| `STATUS.md` | 900 words | generated, read every session |
| `tasks/<ID>.md` | 900 words | 500–800 |
| package `ARCHITECTURE.md` | 400 words | 250–380 |
| package `AGENTS.md` | 200 words | 80–150 |
