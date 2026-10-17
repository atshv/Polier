# ADR-0001: SQLite as the single source of truth

**Date:** 2026-10-17 · **Status:** accepted · **Supersedes:** –

## Context

The CLI needs local persistence. Options: SQLite, a JSON file, a plain text file. JSON would be easier to read, but inflexible for concurrent writes and search. A server is out of the question.

## Decision

SQLite at `~/.bm/bookmarks.db` is the single source of truth. JSON is used only for export and import.

## Consequences

- **Positive:** transactions, indexes, search; no extra infrastructure.
- **Negative:** schema migrations must be maintained.
- **Binds:** `bm/store/`, `bm/portability.py`
- **Prevents:** two data states that drift apart.

## Alternatives

- **JSON file** — rejected: no transactions, slow search, conflicts with concurrent calls.
- **Server + DB** — rejected: contradicts "local, no account".
