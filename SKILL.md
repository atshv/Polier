---
name: polier
description: Plans an AI coding project before any code is written. Interviews the user, drafts a one-page architecture and a task DAG, gets approval, then writes a startable scaffold (ARCHITECTURE.md, AGENTS.md, board.json, STATUS.md, 3–5 task briefs, git repo) that another agent builds from. Use when the user wants to plan, structure or set up a new or existing software project for AI agents, or asks for the next stage of task briefs in a project created this way.
---

# Polier

1. Read [`prompt/generator.md`](prompt/generator.md) completely and follow it; it is the only source of the process. In the DeepSeek Harness, also read [`prompt/dsh.md`](prompt/dsh.md) sections 1–2.
2. If the input block is not filled in, ask for it first.
3. Read other files only when their phase starts:

| Phase | Files |
|---|---|
| C | `templates/ARCHITECTURE.md`, `templates/module-map.md` |
| D | `templates/board.schema.json`, `templates/adr.md` |
| F | `templates/task-brief.md` |
| G | `templates/AGENTS.template.md`, `templates/review-feedback.md` |
| H | `prompt/rubric.md` §3–4 |
| reference | `examples/minimal-cli/` |

4. Run the tools from this folder against the project:

```bash
python3 <skill-folder>/tools/check.py <project>
python3 <skill-folder>/tools/render_status.py <project>
```

When the `pl_check` tool exists (DeepSeek Harness plugin), use it instead of the first command; regenerate `STATUS.md` with the second. In phase G write the real package path into the gate line of `AGENTS.md`, or point to `pl_gate` when the plugin is installed. Before writing the scaffold of a project that already has a task `in_progress`, ask the human to run `/pl lead`.

This package is not part of the project: never copy or commit it there.
