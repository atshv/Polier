# ReviewFeedback — Mxx

> Stored as `reviews/Mxx.md`. Later rounds are appended to the same file as "Round 2", "Round 3" …

```yaml
task_id: Mxx
round: 1
verdict: rework          # pass | rework | fail
acceptance_map:
  A1: pass
  A2: fail
findings:
  - severity: blocker    # blocker | major | minor
    file: "src/<...>"
    line: 42
    criterion: "A2"
    issue: "<What is wrong and why does it matter?>"
    evidence: "<command + output, test name, diff location>"
    fix_hint: "<smallest fix, no rewrite>"
```

## Rules

- No finding without file, line, criterion and evidence.
- No style questions unless they cause defects.
- At most 5 findings per round, most important first.
- The reviewer may not edit code.
- The reviewer sees the diff, acceptance criteria, gate output and architecture, not the author's reasoning.
- `verdict: pass` only when all blockers are gone and the gates are green.
- A `rework` verdict is a new review round: the lead records it with `tools/state.py set <ID> rework --note "..."`, `max_review_rounds` caps the count, and `done` needs `verdict: pass`.
