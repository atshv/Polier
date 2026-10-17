# Projekt-Brief: `bm` — lokale Bookmark-CLI

## Problem

Ich sammle Links in Browser-Lesezeichen, Notizen und Chat-Verläufen. Beim Wiederfinden verliere ich Zeit: Ich weiß, dass ich den Link gesehen habe, aber nicht, wo. Cloud-Dienste will ich nicht; meine Lesezeichen sollen lokal bleiben und ohne Konto funktionieren.

## Ziel

Ein Kommandozeilen-Werkzeug, mit dem ich Links schnell speichern, mit Tags versehen und lokal durchsuchen kann. Ein Befehl, eine Antwort, keine Netzwerkabhängigkeit.

## Nutzer und Nutzung

Ein einzelner Entwickler auf macOS/Linux. Typische Nutzung:

```bash
bm add https://example.com/article --title "Guter Artikel"
bm list
bm search artikel
bm export ~/backup/bookmarks.json
bm import ~/backup/bookmarks.json
```

## MVP (Etappe 1)

- `bm add <url> [--title <t>]` — URL normalisieren, speichern, ID ausgeben
- `bm list` — alle Lesezeichen, neueste zuerst
- `bm search <text>` — in URL und Titel suchen
- `bm export <pfad>` / `bm import <pfad>` — JSON, portabel
- lokale SQLite-Datenbank unter `~/.bm/bookmarks.db`
- Fehlerfälle: ungültige URL, Duplikat, kaputte DB, fehlende Datei

## Nicht-Ziele (V1)

- keine Synchronisation, kein Cloud-Konto
- keine Browser-Extension
- keine Web-Oberfläche
- kein Volltext-Index, kein KI-Tagging
- keine hierarchischen Ordner (nur Tags)
- kein Windows-Support (später)

## Technik

- Python 3.12, `uv`, `typer`, `sqlite3` aus der Standardbibliothek
- Tests: `pytest`; Lint/Typen: `ruff`, `mypy --strict`
- Keine weiteren Laufzeit-Abhängigkeiten ohne Freigabe
- Daten: SQLite; Export/Import als JSON
- Keine Netzwerkaufrufe zur Laufzeit

## Definition of Done

1. `bm add` speichert eine gültige URL und gibt eine ID aus.
2. Dieselbe URL (auch anders geschrieben) wird nicht doppelt gespeichert.
3. `bm list` zeigt alle Einträge, neueste zuerst.
4. `bm search` findet nach URL- und Titel-Substring, unabhängig von Groß-/Kleinschreibung.
5. `bm export` und `bm import` erhalten alle Einträge und Tags.
6. Lint, Typen und Tests sind grün; der E2E-Durchlauf funktioniert auf einer frischen DB.

## Offene Fragen (vor dem Start zu klären)

- Sollen Tags schon in Etappe 1 dabei sein oder erst in Etappe 2? (Annahme: Etappe 2)
- Soll `bm list` eine maximale Anzahl anzeigen? (Annahme: alle, später `--limit`)
- Soll `bm import` bestehende Einträge zusammenführen oder ersetzen? (Annahme: zusammenführen, Duplikate überspringen)
