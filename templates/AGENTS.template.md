# <Project name>

Details: `ARCHITECTURE.md`. Progress: `STATUS.md`. Structure: `docs/module-map.md`. Loop: `docs/orchestration.md`. Line: `docs/factory.md`.

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

- The lead picks work with `pl_next` (first wave only, never a blocked task) and records status with `pl_state` (`in_progress` → `verifying` → `review` → `done`, or `rework`/`blocked`/`failed` with a note; `done` takes the handoff lines). A worker reports and never sets status.
- A worker calls `pl_role <role>` and `pl_task <ID>` first (one claim per task) and works in the task's worktree when the board requires one.
- Gates only with `pl_gate`, names from `board.json`, commands from Commands above; the printed record is the evidence.
- Approvals only with `pl_approval`: a new dependency, merge, release or reopened done task needs a granted record first. Protected paths (`.env`, keys) are lead-only.
- The review packet comes from `pl_review`; later review rounds are appended to `reviews/<ID>.md`.
- The factory line changes only with `pl_factory`; a done task makes its linked items ready.
- Never edit `board.json`, `factory.json`, `runs/` or `reviews/approvals/` by hand. Commit `runs/` and `policy.json` (the rules file).
- Read `ARCHITECTURE.md`, `STATUS.md`, `docs/module-map.md` and your brief first (AGENTS.md is loaded); unclear: `open_questions`, do not guess.
- Stay inside your scope. Check `git status` before finishing; one commit per task (`<ID>: <title>`). No push or PRs without approval.
- Layer direction: UI calls logic, logic calls data, never back.
- Versions only from docs or a manifest; no invented packages.
- No secrets in the repo or bundle; web/mobile bundles are public; secrets live on the server.
- Without the Polier plugin (DeepSeek Harness or Claude Code) the same steps run as `python3 <polier>/tools/<name>.py` (dispatch, state, gate, approve, factory, review).

## Profile L only

- A package imports only what `packages[].may_import` allows (`tools/boundaries.py`; gate `boundaries`).
- Agents never publish; releases run in CI from tags (`docs/releasing.md`).

## Forbidden

- New dependencies, or changed/deleted tests, without approval.
- Placeholders reported as done.
- Architecture invariants changed without an ADR and approval.
- Secrets, tokens or caches committed.
- Hand-edited `board.json`, `factory.json`, `runs/` or `reviews/approvals/`; a task set to `done` without a passing review.
