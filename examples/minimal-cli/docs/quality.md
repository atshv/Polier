# Qualität: bm

## Definition of Done (Projekt)

1. `bm add`, `bm list`, `bm search` funktionieren auf einer frischen DB.
2. Doppelte kanonische URL wird abgelehnt (Exit 2).
3. `bm export` und `bm import` erhalten alle Einträge und Tags.
4. Lint, Typen und Tests sind grün.
5. E2E-Durchlauf auf einer frischen DB ist dokumentiert und läuft.
6. README erklärt Installation und die fünf Kernbefehle.

## Gates

| Gate | Befehl | Erwartet |
|---|---|---|
| Lint | `uv run ruff check .` | keine Fehler |
| Typen | `uv run mypy bm` | keine Fehler |
| Tests | `uv run pytest` | alle grün |
| E2E | `uv run pytest tests/e2e -m e2e` | alle grün |
| Manuell | `bm add` → `bm list` → `bm search` | sichtbare Treffer, Exit 0 |

Ein Gate ist bestanden, wenn Befehl, Exit-Code und erwartete Ausgabe stimmen; die Ausgabe ist die Evidenz. Die Task ist bestanden, wenn alle Gates grün sind, jede Akzeptanz belegt ist und der Reviewer `pass` ohne Blocker gibt.

## Review

- Reviewer ist nicht der Autor.
- Reviewer sieht Diff, Akzeptanz und Gate-Ausgabe, nicht die Denkspur des Autors.
- Jedes Finding: `severity`, `file`, `line`, `criterion`, `evidence`, `fix_hint`.
- Keine Stilfragen, außer sie verursachen Fehler.
- Maximal 5 Findings pro Runde.

## Menschliche Checkliste pro Task

- [ ] Gates wirklich ausgeführt und Ausgabe gesehen.
- [ ] Akzeptanz A1..An einzeln belegt.
- [ ] Diff nur im Scope.
- [ ] Keine Tests ohne Freigabe geändert.
- [ ] Keine Platzhalter/TODOs.
- [ ] `STATUS.md` aus dem Board aktualisiert.
- [ ] Commit mit Task-ID.

## Bewusst nicht geprüft (V1)

- Windows-Kompatibilität
- Performance bei > 10.000 Einträgen
- Barrierefreiheit der CLI (Farben/Screenreader)
- Icons, Web-UI, Sync
