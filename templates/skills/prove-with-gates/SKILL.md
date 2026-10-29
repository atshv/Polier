---
name: Prove it with gates
description: Use before claiming a task works; run every gate through tools/gate.py so the result is recorded.
---

"Tests pass" in a message does not count. Only recorded gate runs do.

- List the gates of your task: `python3 tools/state.py show <ID>`.
- Run each one through the recorder, for example:
  `python3 tools/gate.py --task <ID> --name unit --shell "npm test"`
- A failing gate: read the log tail, fix the cause, run the gate again. Do not edit the record.
- When every gate has a passing record from this attempt, say so and name the gates in the handoff.
