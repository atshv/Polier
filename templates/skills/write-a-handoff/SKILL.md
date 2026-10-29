---
name: Write a handoff
description: Use at the end of every session; finish with a short handoff so the next session, the reviewer and the lead can continue without guessing.
---

End your final message with a section `## Handoff`:

- **Done** — what changed, with file paths.
- **Proof** — the gates you ran and their result.
- **Open** — what is left, known problems, decisions you could not make.
- **For dependants** — at most three short lines that tasks building on this one need to know (new API, changed contract, a gotcha). The lead copies them into the task's `handoff` field on the board; `done` needs it.

Facts only, no narration. Do not edit `board.json` yourself.
