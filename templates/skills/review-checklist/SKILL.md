---
name: Review checklist
description: Use in a reviewer session; check a task against its brief, acceptance and evidence and write a verdict.
---

Read `tasks/<ID>.md`, the diff of the task branch and the gate records in `runs/<ID>.json`. Then check:

1. **Acceptance** — every criterion (A1 …) is met and shown by a test or a recorded gate.
2. **Scope** — only files inside `scope.write` changed.
3. **Architecture** — the rules in `ARCHITECTURE.md` hold (layers, imports, naming, size limits).
4. **Evidence** — every gate of the task has a passing record from the latest attempt.
5. **Risk** — error handling, security-relevant input, migrations and public API changes.

Write `reviews/<ID>.md` with a first line `verdict: pass` or `verdict: fail`, followed by numbered findings. Each finding names the file, the problem and the expected fix. A fail needs at least one finding.
