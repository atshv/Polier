# canvas-mini

Details: `ARCHITECTURE.md`. Progress: `STATUS.md`. Structure: `docs/module-map.md`.

## Commands

- **Setup:** `npm ci` in `packages/ui-kit`, `services/sync` and `apps/web` [VERIFY: lockfiles are written by the first install task]
- **Engine build:** `cmake -S packages/engine -B packages/engine/build && cmake --build packages/engine/build`
- **Engine tests:** `ctest --test-dir packages/engine/build --output-on-failure`
- **WASM build:** `emcmake cmake -S packages/engine -B packages/engine/build-wasm && cmake --build packages/engine/build-wasm`
- **UI kit:** `cd packages/ui-kit && npm run typecheck && npm test`
- **Service:** `cd services/sync && npm run typecheck && npm test`
- **App:** `cd apps/web && npm run typecheck && npm run e2e`
- **Single test:** `cd packages/ui-kit && npm test -- Stage`
- **Boundaries:** `python3 .generator/tools/boundaries.py .`
- **Git status:** `git status --short` · **Diff:** `git diff` · **Recent commits:** `git log --oneline -5`

## Runtime

- Ports and service URLs: only from `.polier-slot` (`python3 .generator/tools/slot.py show`). Never hard-code ports; never touch slot 0's data.
- `e2e` is an exclusive gate: wait for the lock or rerun alone.
- Do not stop processes you did not start: no `kill`, `pkill` or `killall`. Use your slot's ports.

## Rules

- Work only on your task; one claim per task; never take another session's claim. `worktrees: required` — work in the task worktree.
- Read `ARCHITECTURE.md`, `AGENTS.md`, `STATUS.md`, `docs/module-map.md`, the package files and your brief first. Unclear: `open_questions`; do not guess.
- Stay inside your scope: a package task writes inside its package, contract paths are the only exception. Check `git status` before finishing.
- Run every gate with `python3 .generator/tools/gate.py --task <ID> --name <gate> -- <command>`, gate names from `board.json`. Commit `reviews/evidence/` with the task.
- State changes and approvals only with `.generator/tools/state.py` and `approve.py`; never edit `board.json`, `runs/` or `reviews/approvals/` by hand. `dispatch.py` before a task.
- One commit per task (`<ID>: <title>`); no push, no PR without approval.
- Versions only from `docs/versions.md` or a manifest; no invented packages or flags.
- Secrets never in the repo: web bundles are public.

## Profile L only

- A package imports only what `packages[].may_import` allows; gate `boundaries`.
- Contracts live in `contracts/`: change schema, fixtures and every dependant in one task.
- Agents never publish; releases run in CI from tags (`docs/releasing.md`).

## Forbidden

- New dependencies, or changed/deleted tests, without approval.
- Placeholders or TODOs reported as done.
- Architecture invariants changed without an ADR and approval.
- Secrets, tokens or caches committed.
