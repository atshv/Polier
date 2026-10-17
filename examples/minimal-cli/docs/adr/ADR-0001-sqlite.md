# ADR-0001: SQLite als einzige Wahrheit

**Datum:** 17.10.2026 · **Status:** akzeptiert · **Ersetzt:** –

## Kontext

Die CLI braucht lokale Persistenz. Optionen: SQLite, JSON-Datei, einfache Textdatei. JSON wäre einfacher zu lesen, aber bei parallelen Schreibvorgängen und Suche unflexibel. Ein Server kommt nicht infrage.

## Entscheidung

SQLite unter `~/.bm/bookmarks.db` ist die einzige Wahrheit. JSON wird nur für Export und Import verwendet.

## Konsequenzen

- **Positiv:** Transaktionen, Indizes, Suche; keine zusätzliche Infrastruktur.
- **Negativ:** Schema-Migrationen müssen gepflegt werden.
- **Bindet:** `bm/store/`, `bm/portability.py`
- **Verhindert:** zwei Datenstände, die auseinanderlaufen.

## Alternativen

- **JSON-Datei** — verworfen: keine Transaktionen, langsam bei Suche, Konflikt bei parallelen Aufrufen.
- **Server + DB** — verworfen: widerspricht „lokal, kein Konto“.
