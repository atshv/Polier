# Architecture: packages/ui-kit

**As of:** 2026-10-17 · **Kind:** `package` · **Owner:** UI owner

## Purpose

The React component library of canvas-mini: the canvas stage, the toolbar and the design tokens. It is presentation only — no transport, no geometry, no persistence. Not its job: fetching documents, computing hit tests, running sync.

## Inputs

- Props from `apps/web`: a `CanvasHandle` from the engine, the current zoom and toolbar callbacks.
- Contract state (`contracts/state/state.schema.json` 1.0.0) only through props, never through a network client.

## Outputs

- React components (`Stage`, `Toolbar`) and CSS custom properties in `src/theme.css`.
- Component tests and visual references under `tests/` (added by `WEB-01`).

## Invariants

| ID | Rule | Prevents |
|---|---|---|
| P-1 | Every colour, spacing, radius and duration comes from a token in `src/theme.css` (AD-5). | hard-coded values, theme drift |
| P-2 | Every interactive element defines rest, hover, pressed, focus, disabled and error where applicable. | inaccessible or inconsistent controls |
| P-3 | The kit imports only `packages/engine`; no service or app import. | UI code coupled to transport or routing |
| P-4 | Focus is never removed without a visible replacement. | keyboard users losing their place |

## Allowed imports

- `may_import` from `board.json`: `packages/engine`.
- React is a peer dependency; no other third-party UI library.
- Gate: `boundaries` (see root `AGENTS.md`).

## Commands

- **Build:** `npm run build` (`tsc -p tsconfig.json`) → types emitted, no errors.
- **Typecheck:** `npm run typecheck` → no type errors.
- **Tests:** `npm test` (`vitest run`) → all green (component suite added by `WEB-01`).
- **Visual:** `npx playwright test --grep @visual` from `apps/web` → screenshots within tolerance.

## Links

- Root: `../../ARCHITECTURE.md` (AD-2, AD-5), `../../docs/module-map.md`
- Design rules: `../../docs/design-rules.md`
- Contract: `../../contracts/state/README.md`
- Engine types: `../engine/types/index.d.ts`
