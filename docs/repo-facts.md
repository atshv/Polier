# Repository facts: Polier

> Station 1 (idea), brownfield recon (`IDEA-07`). Facts as of 2026-11-12 on `main` at `4214be9`, version 0.4.7. Uncertain points are marked `[UNVERIFIED]`.

## Stack

- Python 3.9+ standard library only (`core/`, `tools/`); Node 20+ ESM without a build step (`plugin/`, `claude/`). No runtime dependency.
- Dev dependencies: `@deepseek-ai/*` 0.2.2-rc.1 (DSH harness packages for tests), `pyflakes` for checks.

## Commands and expected output

| Command | Expected |
| --- | --- |
| `npm install && npm test` | 50 Node tests and 571 Python tests pass (1 skipped) |
| `npm run check` | `OK: generated pages current, no dead code found, modules parse` |
| `python3 tools/check.py tests/fixtures/minimal-cli` | `OK: … passes the mandatory checks.` |
| `python3 tools/audit.py --root tests/fixtures/monorepo-mini` | `audit: 0 error(s), 0 warning(s)` |
| `claude plugin validate . --strict` | `Validation passed` |
| `npm run docs` | rewrites `docs/tools.md`, `docs/roles.md`, `factory/CATALOG.md`, `.claude-plugin/`, `claude/agents/` |

## Structure (two levels)

`core/` rules · `tools/` 22 CLIs · `plugin/` DSH plugin (`lib/`, `test/`) · `claude/` Claude Code adapter (`lib/`, `agents/`, `test/`) · `.claude-plugin/` manifest · `factory/` catalog (176 items, 9 stations) · `roles/` 9 roles · `prompt/` process · `templates/` documents, `gates/`, `store/`, `skills/`, `ui/` · `tests/` with fixtures `minimal-cli` (S) and `monorepo-mini` (L) · `scripts/` · `docs/`.

## Conventions

- One implementation per rule in `core/`; plugins forward to `tools/*.py` (`AGENTS.md`).
- Conventional Commits; `scripts/release.py` releases on every push to `main` (pre-1.0: feat/fix/perf bump the patch).
- Generated pages are checked by `npm run check`; no dead exports.
- Store and legal facts carry `[VERIFY: …]` without a dated source: 64 markers today, most in `templates/gates/` (python 7, cpp-cmake 7, node-ts 6, wasm 6, playwright 5).

## CI, release, secrets

- `.github/workflows/test.yml` on push and PR; `release.yml` on push to `main` tags `vX.Y.Z` and publishes notes. No secrets besides the GitHub token.

## Runtime

- Claims, slots and locks under `<git-common-dir>/polier/`; the Claude Code adapter uses a socket and call registry in the temp folder. Nothing listens on a fixed port.

## Debt and no-go areas

- `docs/guard-limits.md` lists 17 known gaps; the largest: gate records, run records and approvals can be forged by a shell write; commands are matched statically.
- No test measures agent behaviour; tests use real harness packages and fixtures, never module mocks (`AGENTS.md`).
- `prompt/dsh.md` and `prompt/claude-code.md` mark harness details `[UNVERIFIED]` where the harness docs are silent.
- No-go: adding a runtime dependency; private or project-specific content in templates, fixtures or tests.

## Contradictions

- None found between docs and code on `main`.
