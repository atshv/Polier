# Module Structure: <Project name>

> Detail document for `ARCHITECTURE.md`. Contains folders and import rules, no architecture decisions.

## Layers

> **Model:** classic layering. Dependencies only point downwards: UI → logic → data. Domain types live in the logic layer; the data layer does not import them.

| Layer | Folder | Purpose | May import | May not import |
|---|---|---|---|---|
| UI/screens | `<e.g. src/ui/>` | presentation, input | logic, UI components | data/infrastructure directly |
| Logic | `<e.g. src/logic/>` | rules, use cases, domain types | data/infrastructure, own domain types | UI |
| Data/infrastructure | `<e.g. src/data/>` | persistence, DB, adapters | standard library, DB driver, own row types | UI, logic |
| Tests | `<e.g. tests/>` | verification | everything (read-only) | changing production code |

## Folder map

```text
src/
  ui/          # screens, views, view models
  logic/       # use cases, domain types, repository interfaces
  data/        # repositories, DB, API clients, adapters
tests/
  unit/
  e2e/
```

## Data model

- The data model lives in `docs/data-model.md`, not in UI or logic files.
- Tables and columns are defined there; the data layer maps DB rows to its own row types.
- The logic layer knows domain types and repository interfaces, not SQL tables.

## Rules

1. Dependencies only point downwards: UI → logic → data. No cycles.
2. Domain types live in the logic layer; the data layer does not import them but maps to its own row types.
3. The data layer knows neither UI nor logic.
4. New files go into the matching layer; no file "somewhere".
5. A task changes one layer if possible; exceptions are stated in the task brief.
6. The folder map is binding; deviations need an ADR.

## Example (CLI)

```text
bm/
  cli.py          # UI: arguments, output
  service.py      # logic: add/list/search, domain types
  store/          # data: SQLite, repository
  portability.py  # data/adapter: JSON export/import
```
