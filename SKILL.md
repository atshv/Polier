---
name: polier
description: AI software factory. Runs a software project through nine stations — idea, concept, design, architecture, plan, build, verify, release, operate — for web, iOS, Android, desktop, CLI or backend services. Interviews the owner, writes the concept, design rules, a one-page architecture and a task DAG, maps every applicable checklist item (accounts, payments, store listings, privacy, monitoring …) to tasks, then keeps builder agents to the plan with a write guard, recorded gate evidence, reviews and approvals. Use when the user wants to plan, build, release or structure a new or existing software project with AI agents, asks what a website or app needs, or asks for the next station or stage of a project created this way.
---

# Polier — AI software factory

1. Read [`prompt/generator.md`](prompt/generator.md) completely and follow it; it is the only source of the process. In the DeepSeek Harness, also read [`prompt/dsh.md`](prompt/dsh.md) sections 1–2.
2. If the input block is not filled in, ask for it first (`templates/project-input.md`).
3. In a project with `factory.json`, start every session with `python3 <skill-folder>/tools/factory.py next --root <project>` (plugin: `pl_factory`).
4. Read other files only when their station starts:

| Station | Files |
|---|---|
| 1 idea | `templates/project-input.md`, `factory/CATALOG.md` (or `tools/factory.py catalog --platforms … --traits …`); A1 tool check: `tools/factory.py`, `tools/state.py`, `tools/approve.py`, `tools/dispatch.py`, `tools/audit.py`, `tools/slot.py`, `tools/claim.py`, `tools/worktree.py`, `tools/gate.py` |
| 2 concept | `templates/concept.md`; research via `tools/research.py note` |
| 3 design | `templates/ux-flows.md`, `templates/design-rules.md` |
| 4 architecture | `templates/ARCHITECTURE.md`, `templates/module-map.md`, `templates/adr.md`, `templates/versions.md`; L: `templates/monorepo-layout.md`, `templates/package-ARCHITECTURE.md`, `templates/package-AGENTS.md`, `templates/contract.md` |
| 5 plan | `templates/board.schema.json`, `templates/policy.json`, `templates/gates/<stack>.md`, `templates/task-brief.md`, `templates/AGENTS.template.md`, `templates/orchestration.md`, `templates/review-feedback.md`; `prompt/rubric.md` §3–4 |
| 6–7 build, verify | `prompt/orchestration.md`; `templates/skills/` for worker sessions |
| 8 release | `templates/releasing.md`, `templates/environments.md`, `templates/legal.md`, `templates/store/<platform>.md` |
| 9 operate | `templates/runbook.md` |
| reference | `examples/minimal-cli/` (profile S, CLI), `examples/monorepo-mini/` (profile L, web + service) |

5. Run the tools from this folder against the project:

```bash
# the factory line
python3 <skill-folder>/tools/factory.py init --platforms web,ios --traits accounts --root <project>
python3 <skill-folder>/tools/factory.py status|next|check|render --root <project>
python3 <skill-folder>/tools/factory.py done|na|defer|link|advance … --root <project>
# plan and project checks
python3 <skill-folder>/tools/check.py <project>
python3 <skill-folder>/tools/render_status.py <project>
python3 <skill-folder>/tools/research.py check --root <project>
# task loop (projects with policy.json)
python3 <skill-folder>/tools/dispatch.py --root <project>
python3 <skill-folder>/tools/state.py show|set … --root <project>
python3 <skill-folder>/tools/approve.py list --root <project>
python3 <skill-folder>/tools/gate.py --task <ID> --name <gate> --shell "<command>" --root <project>
python3 <skill-folder>/tools/audit.py --root <project>
# profile L, deployments, MCP
python3 <skill-folder>/tools/boundaries.py <project>
python3 <skill-folder>/tools/contracts.py check --root <project>
python3 <skill-folder>/tools/release_check.py <project> --allow-untagged
python3 <skill-folder>/tools/mcp.py --root <project>
```

When the plugin tools exist (DeepSeek Harness: `pl_status`, `pl_gate`, `pl_check`, `pl_next`, `pl_state`, `pl_factory`), use them instead of the matching command. In phase G write the real package path into the gate, state, approval and factory commands of `AGENTS.md` and `docs/orchestration.md`. Write the runtime rules into `AGENTS.md` (ports, database and bucket names only from `.polier-slot`; never hard-code ports; never touch slot 0's data; no `kill`/`pkill`) and the tool rules (state changes only with `tools/state.py`, gates only with `tools/gate.py`, approvals only with `tools/approve.py`, the line only with `tools/factory.py`; never hand-edit `board.json`, `factory.json`, `runs/` or `reviews/approvals/`). Before writing the scaffold of a project that already has a task `in_progress`, ask the human to run `/pl lead`.

This package is not part of the project: never copy or commit it there.
