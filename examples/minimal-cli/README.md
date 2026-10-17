# bm — lokale Bookmark-CLI

Speichert Links lokal in SQLite, listet und durchsucht sie, exportiert und importiert JSON. Kein Konto, kein Netzwerk, keine Cloud.

## Voraussetzungen

- Python 3.12, [`uv`](https://docs.astral.sh/uv/)

## Setup

Voraussetzung: Git-Repo mit `main` und Initial-Commit. Das legt der Generator in Phase G an; M01 legt es nicht noch einmal an.

```bash
uv sync
uv run bm --help
```

## Befehle

```bash
bm add https://example.com --title "Beispiel"
bm list
bm search beispiel
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

## Struktur

| Pfad | Inhalt |
|---|---|
| `bm/cli.py` | Typer-Befehle, Ausgabe |
| `bm/service.py` | Fachlogik (add, list, search) |
| `bm/store/` | SQLite, Schema, Repository |
| `bm/portability.py` | JSON Export/Import |
| `docs/module-map.md` | Schichten und Importregeln |
| `docs/` | Datenmodell, Qualität, ADRs |
| `tasks/` | Task-Briefs (JIT) |

## Dokumentation

- Architektur: `ARCHITECTURE.md`
- Agentenregeln: `AGENTS.md`
- Fortschritt: `STATUS.md`
- Modulstruktur: `docs/module-map.md`
- Datenmodell: `docs/data-model.md`
- Gates: `docs/quality.md`
