# <Project name>

Details: `ARCHITECTURE.md`. Progress: `STATUS.md`. Structure: `docs/module-map.md`.

> Only what an agent would get wrong without it; delete the rest. Max. 400 words.

## Commands

- **Start:** `<...>`
- **Build:** `<...>`
- **All tests:** `<...>`
- **Single test:** `<...>`
- **Lint/types:** `<...>`

## Deviations

- <only rules that differ from the usual; pitfalls, required environment variables>

## Runtime

- Ports, database and bucket names: only from `.polier-slot` (`python3 <package>/tools/slot.py show`). Never hard-code ports; never touch slot 0's data.
- A gate listed in the task's `exclusive` resources (e.g. e2e) never runs concurrently; wait for the lock or rerun alone.
- Do not stop processes you did not start: no `kill`, `pkill` or `killall`. Use your slot's ports.

## Rules

- Work only on your task; one claim per task, never take another session's claim. Use the task's worktree when the board requires one.
- Read `ARCHITECTURE.md`, `AGENTS.md`, `STATUS.md`, `docs/module-map.md` and your brief first. Unclear: `open_questions` in the result; do not guess.
- Run every gate with `pl_gate` or `python3 <package>/tools/gate.py --task <ID> --name <gate> --shell "<command>"`, names from `board.json`. Commit `reviews/evidence/` with the task: the printed record is the evidence.
- Stay inside your scope. One commit per task (`<ID>: <title>`, e.g. `M03: Add, list and search`); check `git status` before finishing. No push or PRs without approval.
- Layer direction: UI calls logic, logic calls data, never back.
- Versions only from docs or a manifest; no invented packages.
- No secrets in the repo or bundle; web/mobile bundles are public. Secrets live on the server.

## Profile L only

- A package imports only what `packages[].may_import` allows (`tools/boundaries.py`; gate `boundaries`).
- Agents never publish; releases run in CI from tags (`docs/releasing.md`).

## Forbidden

- New dependencies, or changed/deleted tests, without approval.
- Placeholders reported as done.
- Architecture invariants changed without an ADR and approval.
- Secrets, tokens or caches committed.
