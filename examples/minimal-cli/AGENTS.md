# bm

Fachliche Details: siehe `ARCHITECTURE.md`. Fortschritt: siehe `STATUS.md`. Struktur: siehe `docs/module-map.md`.

## Befehle

- Setup: `uv sync`
- Starten: `uv run bm --help`
- Alle Tests: `uv run pytest`
- Einzelner Test: `uv run pytest tests/test_service.py -k test_add`
- Lint/Typen: `uv run ruff check . && uv run mypy bm`
- E2E: `uv run pytest tests/e2e -m e2e`
- Git-Status: `git status --short`
- Diff: `git diff`
- Letzte Commits: `git log --oneline -5`

## Abweichungen vom Standard

- Zeitstempel immer UTC als ISO-8601 (`datetime.now(timezone.utc).isoformat()`), nie lokale Zeit.
- SQLite-Verbindung pro CLI-Aufruf öffnen und schließen; keine globalen Connections.
- Externe Programme nur über `subprocess` mit Argumentliste, nie `shell=True`.
- `~/.bm/` wird beim ersten Lauf angelegt; Tests nutzen `tmp_path` und nie das echte Home.

## Regeln

- Arbeite nur am Task, der im Auftrag steht.
- Lies zuerst `ARCHITECTURE.md`, `AGENTS.md`, `STATUS.md`, `docs/module-map.md` und deinen Task-Brief.
- Bei Unklarheit: `open_questions` im Ergebnis, nicht raten.
- Belege Erfolg mit der Ausgabe jedes Gates.
- Ändere keine Dateien außerhalb deines Scopes.
- Ein Commit pro Task: Task-ID + Titel, z. B. `M03: Add, List und Search`. Kein Push, kein Remote.
- Schichten nicht vermischen: CLI ruft Service auf, Service ruft Store – nie umgekehrt.
- Bibliotheken/APIs/Versionen nur aus Doku oder Manifest; keine erfundenen Pakete.

## Verboten

- Neue Abhängigkeiten ohne Freigabe.
- Bestehende Tests ändern oder löschen ohne Freigabe.
- Platzhalter oder TODOs als fertig melden.
- Architektur-Invarianten ändern (nur über ADR + Freigabe).
- Secrets, Tokens oder Caches committen.
