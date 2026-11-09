# Module Structure: bm

> Detail document for `ARCHITECTURE.md`. Folders and import rules, no architecture decisions.

## Layers

| Layer | Folder | Purpose | May import | May not import |
|---|---|---|---|---|
| UI/CLI | `bm/cli.py` | arguments, output, exit codes | `bm.service` | `bm.store` directly |
| Logic | `bm/service.py`, `bm/tags.py` | add/list/search, tag rules | `bm.store`, `bm.config`, `bm.portability` | `bm.cli` |
| Data | `bm/store/` | SQLite, schema, repository | standard library | `bm.cli`, `bm.service` |
| Adapter | `bm/portability.py` | JSON export/import | `bm.store`, standard library | `bm.cli`, `bm.service` |

## Folder map

```text
bm/
  cli.py            # UI/CLI
  service.py        # logic
  tags.py           # logic (stage 2)
  config.py         # configuration
  portability.py    # adapter
  store/
    db.py           # connection, schema, migrations
    repository.py   # data access
tests/
  test_cli.py
  test_service.py
  test_store.py
  test_tags.py
  test_portability.py
  e2e/
```

## Data model

- Tables and fields are in `docs/data-model.md`.
- SQL only in `bm/store/`; CLI and service know no column names.

## Rules

1. Dependencies only point downwards: CLI → service → store; service → portability → store. No cycles.
2. SQL only in `bm/store/`; the CLI contains no queries.
3. The service knows no Typer/CLI types.
4. New files go into the matching layer; no file "somewhere".
5. A task changes one layer if possible. M03 changes CLI + service because the command is wired up; the store stays untouched.
6. Deviations need an ADR.
