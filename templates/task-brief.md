# Mxx — <Name>

> **Größe:** 400–800 Wörter. Kein Brief ohne Kontext-Pack und Gates. Keine Boilerplate – die steht in `AGENTS.md`.

## Ziel

<Ein Satz: was funktioniert nach dieser Aufgabe?>

**Warum:** <welches spätere Modul baut darauf>

## Umfang

- <Funktion 1>
- <Funktion 2>

## Nicht Teil davon

- <bewusst ausgeschlossen> (kommt in Mxx)

## Akzeptanz

A1 WENN <Situation>, DANN SOLL das System <Verhalten>.
A2 WENN <Situation>, DANN SOLL das System <Verhalten>.
A3 ...

## Kontext-Pack

**Lies genau:**

- `ARCHITECTURE.md`, `AGENTS.md`, `STATUS.md`, `docs/module-map.md`
- `docs/contracts/<...>.md`, Abschnitt <...>
- `src/<...>`, Zeilen <...>
- `<Vorbild-Datei>`

**Lies nicht:** <andere Task-Briefs, Details, ...>

**Budget:** ≤ <n> Token Input.

## Vorgaben

- **Schicht/Modul:** <UI/Logik/Daten> — `<Ordner>`
- **Daten/Vertrag:** <Felder, Typen, Grenzen, gemäß ARCHITECTURE.md>
- **Dateien neu:** `<Pfad>`
- **Dateien ändern:** `<Pfad>` — <was genau>
- **Vorbild:** `<bestehende Datei>`

## Stolperfallen

- <Eigenheit einer Bibliothek oder Version> (Quelle: <URL>, geprüft <Datum>)
- <Falle im Projekt, z. B. Feld X heißt in der DB anders>

## Sonderfälle

- <leere Eingabe, Duplikat, ungültiger Wert, fehlende Verbindung, Doppelklick ...>

## Gates

1. `<Befehl>` → <erwartet>
2. `<Befehl>` → <erwartet>
3. <E2E-Szenario> → <sichtbares Ergebnis>

Ein Gate ist bestanden, wenn Befehl, Exit-Code und erwartete Ausgabe stimmen; die Ausgabe ist die Evidenz. Die Task ist bestanden, wenn alle Gates grün sind, jede Akzeptanz belegt ist und der Reviewer `pass` ohne Blocker gibt.

Schlägt ein Gate fehl: Ursache lesen, Code korrigieren, Gate wiederholen. Nie den Test anpassen, damit er grün wird.

## Grenzen

- **Scope:** nur `<Pfade>`
- **Stop:** <max. Runden/Zeit/Token>; bei Blockade `status: blocked` + Begründung
- Keine Architekturänderung; keine neuen Abhängigkeiten ohne Freigabe

## Ausgabe (YAML, kein Prosatext)

```yaml
task_id: Mxx
status: submitted   # submitted | blocked | failed
changed_files: []
evidence: []        # [{gate, command, exit_code, output_tail}]
acceptance: []      # [{id, passed, how}]
open_questions: []
```
