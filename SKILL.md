---
name: polier
description: AI software factory for DeepSeek Harness. Runs a software project through nine stations — idea, concept, design, architecture, plan, build, verify, release, operate — for web, iOS, Android, desktop, CLI or backend services. Interviews the owner, writes the concept, design rules, a one-page architecture and a task DAG, maps every applicable checklist item (accounts, payments, store listings, privacy, monitoring …) to tasks, then keeps builder agents to the plan with a write guard, recorded gate evidence, reviews and owner approvals. Use when the user wants to plan, build, release or structure a new or existing software project with AI agents, asks what a website or app needs, or asks for the next station or stage of a project created this way.
---

# Polier — AI software factory

1. Read [`prompt/generator.md`](prompt/generator.md) completely and follow it; it is the only source of the process. Read [`prompt/dsh.md`](prompt/dsh.md) sections 0–2 for how it runs in DeepSeek Harness.
2. If the input block is not filled in, ask for it first (`templates/project-input.md`), with `ask_user_question` where the answers are closed.
3. Never ask the human to type a command. The `<polier>` block in your context is the live state; the `pl_*` tools change it:

| Intent of the human | Tool |
|---|---|
| start the line | `pl_factory` init with platforms and traits — the owner sees the plan and approves it |
| what is open, what next | read `<polier>`; details with `pl_factory` (next) or `pl_next` |
| record an item | `pl_factory` done (evidence), na or defer (reason), link (tasks) |
| close a station | `pl_factory` advance — the owner answers the approval prompt |
| plan, merge, record status | `pl_mode` lead (owner approves), then `pl_state` |
| take a specialist role | `pl_role` (frontend-builder, backend-builder, reviewer …; `docs/roles.md`) |
| work on a task | `pl_task` (takes the task's role too), then `pl_gate` per gate and `pl_scope_check` |
| delegate a task | fresh subagent: `pl_role` with the task's role, then `pl_task` |
| review | fresh subagent, `pl_role` reviewer, writes `reviews/<ID>.md` |
| a risky action | `pl_approval` — the owner answers the prompt |
| lint the project | `pl_check` |

4. Read other files only when their station starts:

| Station | Files |
|---|---|
| 1 idea | `templates/project-input.md`, `factory/CATALOG.md` (or `tools/factory.py catalog --platforms … --traits …`) |
| 2 concept | `templates/concept.md`; research via `tools/research.py note` |
| 3 design | `templates/ux-flows.md`, `templates/design-rules.md`; web with React + Tailwind: `templates/ui/magic-ui.md` |
| 4 architecture | `templates/ARCHITECTURE.md`, `templates/module-map.md`, `templates/adr.md`, `templates/versions.md`; L: `templates/monorepo-layout.md`, `templates/package-ARCHITECTURE.md`, `templates/package-AGENTS.md`, `templates/contract.md` |
| 5 plan | `templates/board.schema.json`, `templates/policy.json`, `templates/gates/<stack>.md`, `templates/task-brief.md`, `templates/AGENTS.template.md`, `templates/orchestration.md`, `templates/review-feedback.md`; `prompt/rubric.md` §3–4 |
| 6–7 build, verify | `prompt/orchestration.md`, `docs/roles.md`; `templates/skills/` for worker sessions |
| 8 release | `templates/releasing.md`, `templates/environments.md`, `templates/legal.md`, `templates/store/<platform>.md` |
| 9 operate | `templates/runbook.md` |
| reference | `tests/fixtures/minimal-cli/` (profile S), `tests/fixtures/monorepo-mini/` (profile L) |

5. Python tools without a plugin tool, run with `bash` against the project: `tools/research.py`, `tools/worktree.py`, `tools/slot.py`, `tools/audit.py`, `tools/boundaries.py`, `tools/contracts.py`, `tools/release_check.py`, `tools/smoke.py`, `tools/usage.py`. Headless (no approval prompt), the owner uses the matching `tools/*.py` command instead of the prompt.

When scaffolding (station 5) write the gate, state, approval and factory rules into `AGENTS.md` as tool names (`pl_gate`, `pl_state`, `pl_approval`, `pl_factory`) and the runtime rules (ports, database and bucket names only from `.polier-slot`; never hard-code ports; never touch slot 0's data; no `kill`/`pkill`). Never hand-edit `board.json`, `factory.json`, `runs/` or `reviews/approvals/`.

This package is not part of the project: never copy or commit it there.
