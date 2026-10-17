# ReviewFeedback — M03

```yaml
task_id: M03
verdict: rework
acceptance_map:
  A1: pass
  A2: fail
  A3: fail
  A4: pass
  A5: pass
  A6: fail
findings:
  - severity: blocker
    file: "bm/service.py"
    line: 58
    criterion: "A2"
    issue: "Duplikat wird als generischer Fehler behandelt; CLI endet mit Exit 1 statt 2."
    evidence: "pytest tests/test_service.py::test_duplicate_exit_code → AssertionError: expected 2, got 1"
    fix_hint: "IntegrityError in Service in DuplicateUrlError übersetzen; CLI mappt auf Exit 2."
  - severity: major
    file: "bm/cli.py"
    line: 34
    criterion: "A6"
    issue: "Bei DB-Fehler wird der Traceback ausgegeben; die CLI zeigt keine verständliche Meldung."
    evidence: "manuell: DB-Datei auf chmod 000 → Traceback, Exit 1"
    fix_hint: "Service-Fehler fangen, `Datenbank nicht erreichbar` ausgeben, Exit 1, ohne Traceback."
  - severity: minor
    file: "bm/service.py"
    line: 82
    criterion: "A3"
    issue: "Liste sortiert nach id, nicht nach created_at; bei Import kann die Reihenfolge abweichen."
    evidence: "test_list_order legt zwei Einträge mit manipuliertem created_at an → falsche Reihenfolge"
    fix_hint: "ORDER BY created_at DESC, id DESC."
```

## Nächster Schritt

1. Blocker und Major beheben.
2. Tests für A2, A3, A6 ergänzen (nicht bestehende Tests anpassen).
3. Gates erneut ausführen.
4. Review erneut, dann Merge durch den Lead.
