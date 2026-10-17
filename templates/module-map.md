# Modulstruktur: <Projektname>

> Detaildokument zu `ARCHITECTURE.md`. Enthält Ordner und Importregeln, keine Architekturentscheidungen.

## Schichten

> **Modell:** klassische Schichtung. Abhängigkeiten zeigen nur nach unten: UI → Logik → Daten. Domain-Typen liegen in der Logik; die Datenschicht importiert sie nicht.

| Schicht | Ordner | Zweck | Darf importieren | Darf nicht importieren |
|---|---|---|---|---|
| UI/Screens | `<z. B. src/ui/>` | Darstellung, Eingaben | Logik, UI-Bausteine | Daten/Infrastruktur direkt |
| Logik | `<z. B. src/logic/>` | Regeln, Use Cases, Domain-Typen | Daten/Infrastruktur, eigene Domain-Typen | UI |
| Daten/Infrastruktur | `<z. B. src/data/>` | Persistenz, DB, Adapter | Standardbibliothek, DB-Treiber, eigene Row-Typen | UI, Logik |
| Tests | `<z. B. tests/>` | Verifikation | alles (lesend) | Produktionscode ändern |

## Ordnerkarte

```text
src/
  ui/          # Screens, Views, ViewModels
  logic/       # Use Cases, Domain-Typen, Repository-Schnittstellen
  data/        # Repositories, DB, API-Clients, Adapter
tests/
  unit/
  e2e/
```

## Datenmodell

- Das Datenmodell steht in `docs/data-model.md`, nicht in UI- oder Logikdateien.
- Tabellen und Spalten sind dort definiert; die Datenschicht mappt DB-Zeilen auf eigene Row-Typen.
- Die Logik kennt Domain-Typen und Repository-Schnittstellen, keine SQL-Tabellen.

## Regeln

1. Abhängigkeiten zeigen nur nach unten: UI → Logik → Daten. Keine Zyklen.
2. Domain-Typen liegen in der Logik; Data importiert sie nicht, sondern mappt auf eigene Row-Typen.
3. Die Datenschicht kennt weder UI noch Logik.
4. Neue Dateien kommen in die passende Schicht; keine Datei „irgendwo“.
5. Ein Task ändert möglichst eine Schicht; Ausnahmen stehen im Task-Brief.
6. Die Ordnerkarte ist verbindlich; Abweichungen brauchen eine ADR.

## Beispiel (CLI)

```text
bm/
  cli.py          # UI: Argumente, Ausgabe
  service.py      # Logik: add/list/search, Domain-Typen
  store/          # Daten: SQLite, Repository
  portability.py  # Daten/Adapter: JSON Export/Import
```
