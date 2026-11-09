# Architecture: bm

**As of:** 2026-10-17 · **Status:** binding · **Owner:** project team

## 1. Purpose and non-goals

A local bookmark CLI: save links, tag them, search them, back them up as JSON. For a developer who wants to manage bookmarks without a cloud and without an account.

**Non-goals:** sync, cloud, browser extension, web UI, full-text index, AI tagging, Windows.

## 2. Hard constraints

- Python 3.12, `uv`; runtime only standard library + `typer`
- SQLite at `~/.bm/bookmarks.db`; export/import as JSON
- No network calls at runtime; no secrets, no backend
- macOS/Linux; Windows not tested
- Code, comments and CLI texts in English

## 3. System shape and module structure

```text
CLI (typer) → Service → Repository → SQLite
                  ↘ Portability (JSON export/import) → Store
```

- `bm/cli.py` parses arguments and prints output; no domain logic.
- `bm/service.py` contains the operations (add, list, search, import, export).
- `bm/store/` encapsulates SQLite; SQL lives only here.
- `bm/portability.py` reads/writes JSON.
- Direction: CLI → service → store; service → portability → store. The store knows no service, the service no CLI.

Layers: UI/CLI (`bm/cli.py`), logic (`bm/service.py`, `bm/tags.py`), data (`bm/store/`), adapter (`bm/portability.py`). Details: `docs/module-map.md`.

## 4. Invariants

| ID | Rule | Binds | Prevents |
| --- | --- | --- | --- |
| AD-1 | SQLite is the single source of truth; JSON is a backup, not a second store. | store, portability | divergence, duplicate data |
| AD-2 | URLs are canonicalised before saving (lowercase scheme/host, default port removed, trailing slash removed); `url` is unique. | service, store | duplicates, broken search |
| AD-3 | Tags are lowercase, trimmed, max. 20 characters, without commas; duplicates are merged. | service, store | inconsistent filters |
| AD-4 | The CLI contains no domain logic; every operation goes through `bm.service`. | CLI, service | untestable logic, duplicated rules |
| AD-5 | No network calls; import/export only to local paths. | all | unexpected dependencies, privacy |
| AD-6 | Schema changes only via `bm/store/db.py`; no ad-hoc SQL in features. | store, features | drift, broken migrations |

## 5. Boundaries and ownership

| Area | Layer | Write | Read |
| --- | --- | --- | --- |
| `bm/cli.py` | UI/CLI | CLI owner | reviewer |
| `bm/service.py` | logic | logic owner | reviewer |
| `bm/store/` | data | data owner | logic, reviewer |
| `bm/tags.py` | logic | logic owner | reviewer |
| `bm/portability.py` | adapter | adapter owner | service, reviewer |
| `tests/` | quality | everyone | reviewer |

## 6. Quality gates

- Lint: `uv run ruff check .` → no errors
- Types: `uv run mypy bm` → no errors
- Tests: `uv run pytest` → all green
- E2E: `bm add` → `bm list` contains it; `bm search` finds it; duplicate → exit 2

## 7. Open / deferred

- Tags — stage 2 (`ADR-0002`), not in V1
- `--limit` for `list` — after the MVP (`Q1`)
- Windows — not in V1

## 8. References

- Module structure: `docs/module-map.md`
- Data model: `docs/data-model.md`
- Gates/DoD: `docs/quality.md`
- Decisions: `docs/adr/`
