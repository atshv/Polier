# Architektur: bm

**Stand:** 17.10.2026 · **Status:** verbindlich · **Besitzer:** Projektteam

## 1. Zweck und Nicht-Ziele

Eine lokale Bookmark-CLI: Links speichern, taggen, durchsuchen, als JSON sichern. Für einen Entwickler, der Lesezeichen ohne Cloud und ohne Konto verwalten will.

**Nicht-Ziele:** Sync, Cloud, Browser-Extension, Web-UI, Volltext-Index, KI-Tagging, Windows.

## 2. Harte Randbedingungen

- Python 3.12, `uv`; Laufzeit nur Standardbibliothek + `typer`
- SQLite unter `~/.bm/bookmarks.db`; Export/Import als JSON
- Keine Netzwerkaufrufe zur Laufzeit; keine Secrets, kein Backend
- macOS/Linux; Windows nicht getestet
- Code/Kommentare Englisch, CLI-Texte Deutsch

## 3. Systemform und Modulstruktur

```text
CLI (typer) → Service → Repository → SQLite
                  ↘ Portability (JSON export/import) → Store
```

- `bm/cli.py` parst Argumente und gibt aus; keine Fachlogik.
- `bm/service.py` enthält die Operationen (add, list, search, import, export).
- `bm/store/` kapselt SQLite; nur hier steht SQL.
- `bm/portability.py` liest/schreibt JSON.
- Richtung: CLI → Service → Store; Service → Portability → Store. Store kennt keinen Service, Service keine CLI.

Schichten: UI/CLI (`bm/cli.py`), Logik (`bm/service.py`, `bm/tags.py`), Daten (`bm/store/`), Adapter (`bm/portability.py`). Details: `docs/module-map.md`.

## 4. Invarianten

| ID | Regel | Bindet | Verhindert |
| --- | --- | --- | --- |
| AD-1 | SQLite ist die einzige Wahrheit; JSON ist Backup, kein zweiter Store. | Store, Portability | Divergenz, doppelte Datenhaltung |
| AD-2 | URLs werden vor dem Speichern kanonisiert (Schema/Host klein, Standardport weg, Trailing Slash weg); `url` ist eindeutig. | Service, Store | Duplikate, kaputte Suche |
| AD-3 | Tags sind lowercase, getrimmt, max. 20 Zeichen, ohne Kommas; Duplikate werden zusammengeführt. | Service, Store | inkonsistente Filter |
| AD-4 | Die CLI enthält keine Fachlogik; jede Operation geht über `bm.service`. | CLI, Service | nicht testbare Logik, doppelte Regeln |
| AD-5 | Keine Netzwerkaufrufe; Import/Export nur lokale Pfade. | alle | unerwartete Abhängigkeiten, Datenschutz |
| AD-6 | Schemaänderungen nur über `bm/store/db.py`; kein Ad-hoc-SQL in Features. | Store, Features | Drift, kaputte Migrationen |

## 5. Grenzen und Eigentum

| Bereich | Schicht | Schreiben | Lesen |
| --- | --- | --- | --- |
| `bm/cli.py` | UI/CLI | CLI-Verantwortlicher | Reviewer |
| `bm/service.py` | Logik | Logik-Verantwortlicher | Reviewer |
| `bm/store/` | Daten | Daten-Verantwortlicher | Logik, Reviewer |
| `bm/tags.py` | Logik | Logik-Verantwortlicher | Reviewer |
| `bm/portability.py` | Adapter | Adapter-Verantwortlicher | Service, Reviewer |
| `tests/` | Qualität | alle | Reviewer |

## 6. Qualitätsgates

- Lint: `uv run ruff check .` → keine Fehler
- Typen: `uv run mypy bm` → keine Fehler
- Tests: `uv run pytest` → alle grün
- E2E: `bm add` → `bm list` enthält; `bm search` findet; Duplikat → Exit 2

## 7. Offen / Deferred

- Tags — Etappe 2 (`ADR-0002`), nicht V1
- `--limit` für `list` — nach MVP
- Windows — nicht V1

## 8. Verweise

- Modulstruktur: `docs/module-map.md`
- Datenmodell: `docs/data-model.md`
- Gates/DoD: `docs/quality.md`
- Entscheidungen: `docs/adr/`
