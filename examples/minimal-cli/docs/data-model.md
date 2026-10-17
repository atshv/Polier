# Datenmodell: bm

> Detaildokument zu `ARCHITECTURE.md`. Nur Daten, keine Architekturentscheidungen.

## Tabelle `bookmark`

| Feld | Typ | Pflicht | Regeln |
|---|---|---|---|
| `id` | INTEGER | ja | Primärschlüssel, autoincrement |
| `url` | TEXT | ja | kanonisch, eindeutig, max. 2000 Zeichen |
| `title` | TEXT | ja | Standard `''`, max. 500 Zeichen |
| `created_at` | TEXT | ja | ISO-8601 UTC, `datetime.now(timezone.utc).isoformat()` |

**Index:** `UNIQUE(url)`.

## Tabelle `tag` (Etappe 2)

| Feld | Typ | Pflicht | Regeln |
|---|---|---|---|
| `id` | INTEGER | ja | Primärschlüssel |
| `name` | TEXT | ja | lowercase, getrimmt, max. 20 Zeichen, eindeutig |

## Tabelle `bookmark_tag` (Etappe 2)

| Feld | Typ | Pflicht | Regeln |
|---|---|---|---|
| `bookmark_id` | INTEGER | ja | Fremdschlüssel `bookmark.id`, `ON DELETE CASCADE` |
| `tag_id` | INTEGER | ja | Fremdschlüssel `tag.id`, `ON DELETE CASCADE` |

**Primärschlüssel:** (`bookmark_id`, `tag_id`).

## Regeln

- SQLite-Fremdschlüssel aktivieren (`PRAGMA foreign_keys = ON`) pro Verbindung.
- Schemaänderungen nur in `bm/store/db.py` mit einer nummerierten Migration.
- Kein Ad-hoc-SQL außerhalb von `bm/store/`.
- Export/Import nutzt dieselben Tabellen; JSON ist kein zweites Schema.
