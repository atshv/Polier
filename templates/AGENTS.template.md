# <Project name>

Details: `ARCHITECTURE.md`. Progress: `STATUS.md`. Structure: `docs/module-map.md`. Loop: `docs/orchestration.md`.

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

- Ports, DB and bucket names only from `.polier-slot` (`tools/slot.py show`); never hard-code ports or touch slot 0's data.
- A gate in the task's `exclusive` resources (e.g. e2e) never runs concurrently: wait or rerun alone.
- Do not stop processes you did not start: no `kill`, `pkill`, `killall`.

## Task loop

- Start from `python3 <package>/tools/dispatch.py`: take the first wave, never a blocked task.
- One claim per task; work in its worktree when the board requires one.
- The lead records status with `python3 <package>/tools/state.py set <ID> <status>` (`in_progress` → `verifying` → `review` → `done`, or `rework`/`blocked`/`failed` with a note) and runs `tools/render_status.py` afterwards; a worker reports and never sets status or edits `board.json`.
- Gates only with `pl_gate` or `python3 <package>/tools/gate.py --task <ID> --name <gate> --shell "<command>"`, names from `board.json`; the printed record is the evidence, committed with `reviews/evidence/`.
- Approvals only with `python3 <package>/tools/approve.py request|grant|deny`; a new dependency, merge, release or reopened done task needs a granted record in `reviews/approvals/` first. Protected paths (`.env`, keys) are lead-only.
- `runs/<ID>.json` is the execution record; never edit `runs/`, `reviews/approvals/` or `board.json` by hand. Commit `runs/` and `policy.json` (the rules file).
- Read `ARCHITECTURE.md`, `STATUS.md`, `docs/module-map.md` and your brief first (AGENTS.md is loaded); unclear: `open_questions`, do not guess.
- Stay inside your scope. One commit per task (`<ID>: <title>`); check `git status` before finishing. No push or PRs without approval.
- Layer direction: UI calls logic, logic calls data, never back.
- Versions only from docs or a manifest; no invented packages.
- No secrets in the repo or bundle; web/mobile bundles are public; secrets live on the server.

## Profile L only

- A package imports only what `packages[].may_import` allows (`tools/boundaries.py`; gate `boundaries`).
- Agents never publish; releases run in CI from tags (`docs/releasing.md`).

## Forbidden

- New dependencies, or changed/deleted tests, without approval.
- Placeholders reported as done.
- Architecture invariants changed without an ADR and approval.
- Secrets, tokens or caches committed.
- Hand-edited `board.json`, `runs/` or `reviews/approvals/`; a task set to `done` without a passing review.
