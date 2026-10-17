# bm

Domain details: see `ARCHITECTURE.md`. Progress: see `STATUS.md`. Structure: see `docs/module-map.md`.

## Commands

- Setup: `uv sync`
- Start: `uv run bm --help`
- All tests: `uv run pytest`
- Single test: `uv run pytest tests/test_service.py -k test_add`
- Lint/types: `uv run ruff check . && uv run mypy bm`
- E2E: `uv run pytest tests/e2e -m e2e`
- Git status: `git status --short`
- Diff: `git diff`
- Recent commits: `git log --oneline -5`

## Deviations from the standard

- Timestamps always UTC as ISO 8601 (`datetime.now(timezone.utc).isoformat()`), never local time.
- Open and close the SQLite connection per CLI call; no global connections.
- External programs only via `subprocess` with an argument list, never `shell=True`.
- `~/.bm/` is created on the first run; tests use `tmp_path` and never the real home directory.

## Rules

- Work only on the task in your work order.
- First read `ARCHITECTURE.md`, `AGENTS.md`, `STATUS.md`, `docs/module-map.md` and your task brief.
- If anything is unclear: `open_questions` in the result; do not guess.
- Prove success with the output of every gate.
- Do not change files outside your scope.
- One commit per task: task ID + title, e.g. `M03: Add, list and search`. No push, no remote.
- Do not mix layers: the CLI calls the service, the service calls the store, never the other way round.
- Libraries/APIs/versions only from docs or a manifest; no invented packages.

## Forbidden

- New dependencies without approval.
- Changing or deleting existing tests without approval.
- Reporting placeholders or TODOs as done.
- Changing architecture invariants (only via ADR + approval).
- Committing secrets, tokens or caches.
