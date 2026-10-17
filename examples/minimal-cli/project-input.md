# Generator Input: `bm` — Local Bookmark CLI

> This is the input the generator received (the filled-in input block from `generator.md` plus background). It is not part of the generated project.

```text
PROJECT:
A command-line tool that saves links locally, lists them and searches them,
and exports/imports them as JSON. For a single developer on macOS/Linux who
wants bookmarks without a cloud service or an account. Success: a link saved
once is found again with one command. Out of scope: sync, browser extension,
web UI, full-text index, AI tagging, Windows.

MODE:
greenfield

PROFILE:
don't know

LANGUAGE:
everything in English

BUDGET:
a few evenings; no paid services

EXISTING REPO:
none
```

## Problem

I collect links in browser bookmarks, notes and chat histories. When I want to find one again I lose time: I know I have seen the link, but not where. I don't want cloud services; my bookmarks should stay local and work without an account.

## Users and usage

A single developer on macOS/Linux. Typical usage:

```bash
bm add https://example.com/article --title "Good article"
bm list
bm search article
bm export ~/backup/bookmarks.json
bm import ~/backup/bookmarks.json
```

## MVP

- `bm add <url> [--title <t>]` — normalise the URL, save it, print the ID
- `bm list` — all bookmarks, newest first
- `bm search <text>` — search URL and title
- `bm export <path>` / `bm import <path>` — JSON, portable
- local SQLite database at `~/.bm/bookmarks.db`
- error cases: invalid URL, duplicate, broken DB, missing file

## Tech

- Python 3.12, `uv`, `typer`, `sqlite3` from the standard library
- Tests: `pytest`; lint/types: `ruff`, `mypy --strict`
- No further runtime dependencies without approval
- No network calls at runtime

## Definition of done

1. `bm add` saves a valid URL and prints an ID.
2. The same URL (even written differently) is not saved twice.
3. `bm list` shows all entries, newest first.
4. `bm search` finds by URL and title substring, case-insensitively.
5. `bm export` and `bm import` preserve all entries and tags.
6. Lint, types and tests are green; the E2E run works on a fresh DB.

## Open questions (to clarify before the start)

- Should tags be part of stage 1 or stage 2? (Assumption: stage 2 — became `ADR-0002`.)
- Should `bm list` show a maximum number of entries? (Assumption: all, `--limit` later — still open as `Q1`.)
- Should `bm import` merge or replace existing entries? (Assumption: merge, skip duplicates.)
