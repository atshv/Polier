# <Project name>

Domain details: see `ARCHITECTURE.md`. Progress: see `STATUS.md`. Structure: see `docs/module-map.md`.

> **Rule:** only rules that apply to every task. Delete every line the AI would get right without it. No architecture, no progress, no long explanations. Max. 400 words.

## Commands

- **Start:** `<...>`
- **Build:** `<...>`
- **All tests:** `<...>`
- **Single test:** `<...>`
- **Lint/types:** `<...>`
- **Git status:** `git status --short`
- **Diff:** `git diff`
- **Recent commits:** `git log --oneline -5`

## Deviations from the standard

- <only rules that differ from the usual>
- <known pitfalls of the environment, required environment variables>

## Rules

- Work only on the task in your work order.
- First read `ARCHITECTURE.md`, `AGENTS.md`, `STATUS.md`, `docs/module-map.md` and your task brief.
- If anything is unclear: `open_questions` in the result; do not guess.
- Prove success with the output of every gate.
- Do not change files outside your scope.
- One commit per task: task ID + title, e.g. `M03: Add, list and search`. No push, no remote, no PRs without approval.
- Do not mix layers: UI calls logic, logic calls data, never the other way round.
- Libraries/APIs/versions only from docs or a manifest; no invented packages.
- Secrets: no keys/tokens in the repo or bundle. Mobile/web bundles are public (Expo: `EXPO_PUBLIC_*`); secrets only on the server.

## Forbidden

- New dependencies without approval.
- Changing or deleting existing tests without approval.
- Reporting placeholders or TODOs as done.
- Changing architecture invariants (only via ADR + approval).
- Committing secrets, tokens or caches.
