---
name: Stay in scope
description: Use before every file change; keep writes inside the task's scope.write and report anything outside it.
---

- Before you edit a file, check that its path is inside `scope.write` of your task (`python3 tools/state.py show <ID>`).
- A needed change outside the scope is a plan change, not a quick fix. Stop and write in the handoff which file, why, and which task should own it.
- Never touch `board.json`, `policy.json`, `runs/` or another task's brief.
- Keep the diff small: no drive-by refactors, no formatting of untouched lines, no renamed files the brief does not ask for.
