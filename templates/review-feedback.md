# ReviewFeedback — Mxx

```yaml
task_id: Mxx
verdict: rework          # pass | rework | fail
acceptance_map:
  A1: pass
  A2: fail
findings:
  - severity: blocker    # blocker | major | minor
    file: "src/<...>"
    line: 42
    criterion: "A2"
    issue: "<Was ist falsch und warum ist es wichtig?>"
    evidence: "<Befehl + Ausgabe, Testname, Diff-Stelle>"
    fix_hint: "<kleinste Korrektur, kein Rewrite>"
```

## Regeln

- Kein Finding ohne Datei, Zeile, Kriterium und Evidenz.
- Keine Stilfragen, außer sie verursachen Fehler.
- Maximal 5 Findings pro Runde, die wichtigsten zuerst.
- Der Reviewer darf nicht editieren.
- Der Reviewer sieht Diff, Akzeptanz, Gate-Ausgabe und Architektur – nicht die Denkspur des Autors.
- `verdict: pass` nur, wenn alle Blocker weg sind und die Gates grün sind.
