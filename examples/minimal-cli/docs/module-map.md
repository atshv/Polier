# Modulstruktur: bm

> Detaildokument zu `ARCHITECTURE.md`. Ordner und Importregeln, keine Architekturentscheidungen.

## Schichten

| Schicht | Ordner | Zweck | Darf importieren | Darf nicht importieren |
|---|---|---|---|---|
| UI/CLI | `bm/cli.py` | Argumente, Ausgabe, Exit-Codes | `bm.service` | `bm.store` direkt |
| Logik | `bm/service.py`, `bm/tags.py` | add/list/search, Tag-Regeln | `bm.store`, `bm.config`, `bm.portability` | `bm.cli` |
| Daten | `bm/store/` | SQLite, Schema, Repository | Standardbibliothek | `bm.cli`, `bm.service` |
| Adapter | `bm/portability.py` | JSON Export/Import | `bm.store`, Standardbibliothek | `bm.cli`, `bm.service` |

## Ordnerkarte

```text
bm/
  cli.py            # UI/CLI
  service.py        # Logik
  tags.py           # Logik (Etappe 2)
  config.py         # Konfiguration
  portability.py    # Adapter
  store/
    db.py           # Verbindung, Schema, Migration
    repository.py   # Datenzugriff
tests/
  test_cli.py
  test_service.py
  test_store.py
  test_tags.py
  test_portability.py
  e2e/
```

## Datenmodell

- Tabellen und Felder stehen in `docs/data-model.md`.
- SQL nur in `bm/store/`; CLI und Service kennen keine Spaltennamen.

## Regeln

1. Abhängigkeiten zeigen nur nach unten: CLI → Service → Store; Service → Portability → Store. Keine Zyklen.
2. SQL nur in `bm/store/`; die CLI enthält keine Queries.
3. Der Service kennt keine Typer-/CLI-Typen.
4. Neue Dateien kommen in die passende Schicht; keine Datei „irgendwo“.
5. Ein Task ändert möglichst eine Schicht. M03 ändert CLI + Service, weil der Befehl verdrahtet wird – Store bleibt unangetastet.
6. Abweichungen brauchen eine ADR.
