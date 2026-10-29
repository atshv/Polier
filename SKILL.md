---
name: polier
description: Plans an AI coding project before any code is written. Interviews the user, drafts a one-page architecture and a task DAG, gets approval, then writes a startable scaffold (ARCHITECTURE.md, AGENTS.md, board.json, STATUS.md, 3–5 task briefs, git repo) that another agent builds from; while it builds, it records attempts, gate evidence and approvals. Use when the user wants to plan, structure or set up a new or existing software project for AI agents, or asks for the next stage of task briefs in a project created this way.
---

# Polier

1. Read [`prompt/generator.md`](prompt/generator.md) completely and follow it; it is the only source of the process. In the DeepSeek Harness, also read [`prompt/dsh.md`](prompt/dsh.md) sections 1–2.
2. If the input block is not filled in, ask for it first.
3. Read other files only when their phase starts:

| Phase | Files |
|---|---|
| A1 | check for `tools/slot.py`, `tools/claim.py`, `tools/worktree.py`, `tools/gate.py` (runtime) and `tools/state.py`, `tools/approve.py`, `tools/dispatch.py`, `tools/audit.py` (1.1 orchestration); with the plugin, `pl_next` and `pl_state` |
| C | `templates/ARCHITECTURE.md`, `templates/module-map.md`; L: `templates/monorepo-layout.md`, `templates/package-ARCHITECTURE.md`, `templates/package-AGENTS.md` |
| D | `templates/board.schema.json`, `templates/policy.json`, `templates/adr.md`, `templates/versions.md`, `templates/gates/<stack>.md`; L: `templates/contract.md` |
| A, B, F | research: `templates/research-note.md` via `tools/research.py note`, versions via `tools/research.py versions --lookup --write` |
| F | `templates/task-brief.md`; UI: `templates/design-rules.md` |
| G | `templates/AGENTS.template.md`, `templates/orchestration.md`, `templates/review-feedback.md`, `templates/releasing.md`, `templates/environments.md` |
| H | `prompt/rubric.md` §3–4 |
| reference | `examples/minimal-cli/` (profile S), `examples/monorepo-mini/` (profile L); `prompt/orchestration.md` when a task state, an approval or the run records are involved |

4. Run the tools from this folder against the project:

```bash
python3 <skill-folder>/tools/check.py <project>
python3 <skill-folder>/tools/render_status.py <project>
python3 <skill-folder>/tools/research.py check --root <project>
# 1.1: only when the project has a policy.json
python3 <skill-folder>/tools/dispatch.py --root <project>
python3 <skill-folder>/tools/audit.py --root <project>
python3 <skill-folder>/tools/state.py show --root <project>
python3 <skill-folder>/tools/approve.py list --root <project>
# optional 2.0 dashboard (local, no dependencies) and MCP host bridge
python3 <skill-folder>/tools/serve.py <project> --port 8765
python3 <skill-folder>/tools/mcp.py --root <project>
# 2.1 project cockpit: settings, labels, saved views, plan edits
python3 <skill-folder>/tools/settings.py show --root <project>
python3 <skill-folder>/tools/views.py list --root <project>
python3 <skill-folder>/tools/plan.py create --help
# 2.3 knowledge and intake
python3 <skill-folder>/tools/pages.py list --root <project>
python3 <skill-folder>/tools/intake.py list --root <project>
python3 <skill-folder>/tools/templates.py list --root <project>
# 2.4 intelligence (read-only)
python3 <skill-folder>/tools/assistant.py ask "What is blocking?" --root <project>
python3 <skill-folder>/tools/automations.py run --root <project>
python3 <skill-folder>/tools/github.py status --root <project>
# 2.2 planning view data (read-only): timeline, cycles, modules, coverage, analytics
python3 -c "print('see tools/serve.py for the dashboard; board schema 1.2 adds planned_start/target')"
# profile L only
python3 <skill-folder>/tools/boundaries.py <project>
python3 <skill-folder>/tools/contracts.py check --root <project>
# projects that deploy
python3 <skill-folder>/tools/release_check.py <project> --allow-untagged
```

When the `pl_check` tool exists (DeepSeek Harness plugin), use it instead of the first command; regenerate `STATUS.md` with the second. In phase G write the real package path into the gate line of `AGENTS.md`, or point to `pl_gate` when the plugin is installed, and into the state and approval commands of `AGENTS.md` and `docs/orchestration.md`. Write the runtime rules into `AGENTS.md` (ports, database and bucket names only from `.polier-slot`; never hard-code ports; never touch slot 0's data; no `kill`/`pkill`) and the 1.1 rules (state changes only with `tools/state.py`, gates only with `tools/gate.py`, approvals only with `tools/approve.py`, never hand-edit `board.json`/`runs/`/`reviews/approvals/`). `tools/state.py`, `tools/approve.py` and `tools/dispatch.py` read `policy.json`; a 0.9/1.0 project without it is not broken by 1.1 (the transition table and note rules still hold, the rest warns), so mention these tools only in projects that get one. `examples/minimal-cli` is the 0.9 compatibility reference; `examples/monorepo-mini` is the 1.1 reference. Before writing the scaffold of a project that already has a task `in_progress`, ask the human to run `/pl lead`.

This package is not part of the project: never copy or commit it there.
