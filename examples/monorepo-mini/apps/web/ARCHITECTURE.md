# Architecture: apps/web

**As of:** 2026-10-17 · **Kind:** `app` · **Owner:** app owner

## Purpose

The deployable Web app of canvas-mini: it composes the engine, the UI kit and the sync client into the editor route. It owns routing, the transport client and the page shell. Not its job: geometry, component styling, sync rules.

## Inputs

- `@canvas/engine` — WASM module and types of the scene core.
- `@canvas/ui-kit` — `Stage`, `Toolbar` and the design tokens.
- `@canvas/sync` — the `CanvasState` type and contract version 1.0.0.
- The sync service over HTTP on the slot port; environment variables from `docs/environments.md`.

## Outputs

- The editor page at `/` of the deployment; the sync client module in `src/lib/`.
- Playwright e2e and visual references under `tests/e2e/` (added by `WEB-02`).

## Invariants

| ID | Rule | Prevents |
|---|---|---|
| P-1 | The app is the only place that wires engine, kit and service together (AD-2). | duplicated wiring in packages |
| P-2 | Data from the service is validated with `validateState` before it reaches the stage. | rendering an invalid document |
| P-3 | UI values come from the UI kit tokens; the app adds no colour or spacing literals (AD-5). | visual drift |
| P-4 | The sync URL comes from `NEXT_PUBLIC_SYNC_URL`, never from a hard-coded host. | broken previews, slot collisions |

## Allowed imports

- `may_import` from `board.json`: `packages/engine`, `packages/ui-kit`, `services/sync`.
- No import into another app or a package internal.
- Gate: `boundaries` (see root `AGENTS.md`).

## Commands

- **Dev:** `npm run dev` on the slot port (`web` offset 0).
- **Build:** `npm run build` (`next build`).
- **Typecheck:** `npm run typecheck` → no type errors.
- **E2E:** `npm run e2e` (`playwright test`, exclusive resource `e2e`) → full flow green.

## Links

- Root: `../../ARCHITECTURE.md` (AD-1, AD-2, AD-3, AD-5), `../../docs/module-map.md`
- Design rules: `../../docs/design-rules.md`
- Contract: `../../contracts/state/README.md`
- Environments: `../../docs/environments.md`
