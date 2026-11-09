# bm — local bookmark CLI

Saves links locally in SQLite, lists and searches them, exports and imports JSON. No account, no network, no cloud.

## Requirements

- Python 3.12, [`uv`](https://docs.astral.sh/uv/)

## Setup

The git repo with `main` and an initial commit is created by the generator in phase G; M01 does not create it again.

```bash
uv sync
uv run bm --help
```

## Commands

```bash
bm add https://example.com --title "Example"
bm list
bm search example
bm export ~/backup/bookmarks.json
bm import ~/backup/bookmarks.json
```

## Tests

```bash
uv run ruff check .
uv run mypy bm
uv run pytest
uv run pytest tests/e2e -m e2e
```

## Structure

| Path | Contents |
|---|---|
| `bm/cli.py` | Typer commands, output |
| `bm/service.py` | domain logic (add, list, search) |
| `bm/store/` | SQLite, schema, repository |
| `bm/portability.py` | JSON export/import |
| `docs/` | module map, data model, quality, ADRs |
| `tasks/` | task briefs (JIT) |
| `reviews/` | review results per task |

## Documentation

- Architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- Agent rules: [`AGENTS.md`](AGENTS.md)
- Progress: [`STATUS.md`](STATUS.md)
- Module structure: [`docs/module-map.md`](docs/module-map.md)
- Data model: [`docs/data-model.md`](docs/data-model.md)
- Gates: [`docs/quality.md`](docs/quality.md)
