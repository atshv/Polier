# Data Model: bm

> Detail document for `ARCHITECTURE.md`. Data only, no architecture decisions.

## Table `bookmark`

| Field | Type | Required | Rules |
|---|---|---|---|
| `id` | INTEGER | yes | primary key, autoincrement |
| `url` | TEXT | yes | canonical, unique, max. 2000 characters |
| `title` | TEXT | yes | default `''`, max. 500 characters |
| `created_at` | TEXT | yes | ISO 8601 UTC, `datetime.now(timezone.utc).isoformat()` |

**Index:** `UNIQUE(url)`.

## Table `tag` (stage 2)

| Field | Type | Required | Rules |
|---|---|---|---|
| `id` | INTEGER | yes | primary key |
| `name` | TEXT | yes | lowercase, trimmed, max. 20 characters, unique |

## Table `bookmark_tag` (stage 2)

| Field | Type | Required | Rules |
|---|---|---|---|
| `bookmark_id` | INTEGER | yes | foreign key `bookmark.id`, `ON DELETE CASCADE` |
| `tag_id` | INTEGER | yes | foreign key `tag.id`, `ON DELETE CASCADE` |

**Primary key:** (`bookmark_id`, `tag_id`).

## Rules

- Enable SQLite foreign keys (`PRAGMA foreign_keys = ON`) per connection.
- Schema changes only in `bm/store/db.py` with a numbered migration.
- No ad-hoc SQL outside `bm/store/`.
- Export/import uses the same tables; JSON is not a second schema.
