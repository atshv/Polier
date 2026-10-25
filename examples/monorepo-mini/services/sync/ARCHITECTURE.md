# Architecture: services/sync

**As of:** 2026-10-17 · **Kind:** `service` · **Owner:** sync owner

## Purpose

The sync service of canvas-mini: it holds the current document per document id, validates every incoming change against the state contract and broadcasts accepted revisions to connected clients. It serves no HTML, runs no geometry and imports no UI code (AD-2). Not its job: persistence, accounts, rendering.

## Inputs

- HTTP requests from `apps/web` on the slot port (`web` +0, `api` +1 from `.polier-slot`).
- Document messages conforming to `contracts/state/state.schema.json` 1.0.0; anything with another contract version is rejected.

## Outputs

- `GET /health` → `{"status":"ok","contract":"1.0.0"}` for the smoke check.
- Accepted revisions fanned out to every connected client of the document; rejected messages return a problem list.

## Invariants

| ID | Rule | Prevents |
|---|---|---|
| P-1 | A document is accepted only when the contract version matches `CONTRACT_VERSION` (AD-3). | mixed client versions, half-applied updates |
| P-2 | Revisions are immutable and monotonic; a client never receives an older revision after a newer one. | flicker, lost updates |
| P-3 | The service keeps state in memory only in 1.0; no disk write. | undocumented persistence, data leaks |

## Allowed imports

- `may_import` from `board.json`: `packages/engine`.
- Node built-ins only; no UI package, no app import, no browser global.
- Gate: `boundaries` (see root `AGENTS.md`).

## Commands

- **Build:** `npm run build` (`tsc -p tsconfig.json`).
- **Typecheck:** `npm run typecheck` → no type errors.
- **Tests:** `npm test` (`vitest run`) → all green (suite added by `API-01`).
- **Smoke:** `python3 .generator/tools/smoke.py --url http://localhost:4100 --expect-status 200 --path /` after a deploy.

## Links

- Root: `../../ARCHITECTURE.md` (AD-1, AD-2, AD-3), `../../docs/module-map.md`
- Contract: `../../contracts/state/README.md`
- Environments: `../../docs/environments.md`
