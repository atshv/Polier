# DeepSeek Harness: How Polier Runs Inside It

Polier is built for the DeepSeek Harness (DSH). This file maps the stations of `prompt/generator.md` and the running project to the DSH tools that do them best.

> **Verified (2026-11-09)** against `@deepseek-ai/dsh` 0.2.2-rc.1 (READMEs and type declarations of `dsh-system-prompt`, `dsh-tools`, `dsh-user-approval`, `dsh-goal`, `dsh-tool-goal`, `dsh-tool-subagent`, `dsh-tool-ralph`, `dsh-workflow`) and this package. Details the packages do not state are marked `[UNVERIFIED]`.

## 0. What the plugin gives every session

| Seam | What Polier does with it |
|---|---|
| `ctx.systemPrompt.context` | The live `<polier>` block in every step: project, role, station with open items, running task with scope and gates, ready tasks, limits, pending approvals, next move. Empty outside a Polier project. |
| `ctx.systemPrompt.section` | A short guide and the active specialist role's instructions. |
| `ctx.approval` | Every owner decision is a DSH approval prompt: `pl_mode lead`/`off`, `pl_factory init`/`advance`, `pl_approval`. Without an answerer (headless) it fails closed. |
| `tools/pre-execute` + `ctx.tools.guard` | Every write and `bash` command is checked by `tools/guard.py` (scope, role, policy); claim heartbeats; the kill warning. |
| `agent/turn-stopping` | The stop check: git diff against the task scope, sent back to the agent. |
| `ctx.skills` | The `polier` skill. |

The owner talks plainly ("weiter", "what is missing?", "close the station", "take M03"); the agent calls the matching tool. Every tool and parameter is in [`docs/tools.md`](../docs/tools.md). The Python tools in `tools/` are the one implementation underneath and the headless path.

## 1. What a session can do

DSH composes its tools from packages. In station 1, check the tool list and use the fallback for anything missing.

| Capability | Tools | Availability |
|---|---|---|
| Files, shell, search | `read`, `write`, `edit`, `bash`, `glob`, `grep` | standard |
| Background jobs | `bash` with `run_in_background`, `job_output` | job registry |
| Structured questions | `ask_user_question` | `dsh-tool-ask-user` |
| Plan mode | `/plan`, `exit_plan_mode` | `dsh-plan-mode` |
| Checklist | `todo_write` | `dsh-tool-todo` |
| Web research | `web_search`, `web_fetch` | `dsh-tool-web` |
| Subagents | `subagent`, `send_message`, `interrupt_agent`, `list_subagent_models` | `dsh-tool-subagent` |
| Parallel read-only agents | `workflow` | `dsh-tool-workflow` |
| Long objectives | `create_goal`, `get_goal`, `update_goal` | `dsh-tool-goal` |
| Deliverables | `present` (max. 4 files) | `dsh-tool-present` |
| Agent Teams | `spawn_teammate`, `wait_agent`, `team_task_*` | **experimental**, off by default |
| Worktrees | `create_worktree` | **experimental**, off by default |

- **`AGENTS.md` is loaded automatically**, from the project root down to the working directory (L: also `<package>/AGENTS.md`). Never paste it; keep it within budget.
- **Plan mode is guidance, not enforcement.** The sandbox, the approval policy and the Polier guard decide what runs.

## 2. Station → tool

| Station / step | Use | Fallback |
|---|---|---|
| all | `todo_write`, one item per station | none needed |
| any station the owner wants finished | `create_goal` ("Close station concept: resolve every open item with evidence"); the `<polier>` block shows what is left each round | turn by turn |
| 1 interview | `ask_user_question`, max. 10 per call, options with the recommended one first | chat |
| 1 start the line | `pl_factory` init (approval prompt) | `tools/factory.py init` |
| 1–5 facts | `web_search`, `web_fetch`; record with `tools/research.py` | `[UNVERIFIED]` + ask |
| 1 brownfield recon | read-only `subagent`s or `workflow`, one per top-level area, cheaper model | main session reads |
| 4+5 approval | `/plan` + `exit_plan_mode`: architecture, DAG table, Mermaid (L: package map, stages, contracts) | chat, wait for "yes" |
| 4, 5 critics (M/L) | `workflow`: architecture critic, scope critique, test design in parallel, findings only | three `subagent` calls |
| 5 cold start + rubric | fresh `subagent`, then `send_message` to the same child | second fresh `subagent` |
| 5 lint | `pl_check`, `pl_next` | `bash` |
| 5 handoff | `present`: `ARCHITECTURE.md`, `AGENTS.md`, `STATUS.md`, `tasks/M01.md` | file tree in chat |
| every close | `pl_factory advance` (approval prompt) | `tools/factory.py advance --by <owner>` |

Subagents and `workflow` only read, research and criticise during planning.

## 3. Running the project

| Step | Lead session | Worker session |
|---|---|---|
| choose | `pl_next` (waves, blocked tasks, conflicts) | — |
| start | worktree when required, `pl_state` → `in_progress` | `pl_role <role>`, `pl_task M03` (binds and claims) |
| build | — | code inside the scope, `pl_gate` per gate, `pl_scope_check` |
| check | `pl_state` → `verifying`, `review` | — |
| review | `pl_review` packet to a fresh reviewer subagent, which appends a round to `reviews/M03.md` | — |
| close | `pl_state` → `done` (with handoff lines) or `rework`; `pl_factory done` for linked items; commit | — |

`STATUS.md` and `docs/factory.md` regenerate after every recorded change. Checkpoints, attempts, rounds, approvals and budgets are described once, in `prompt/orchestration.md`. DSH does not hand token counts to plugins: with a budget the lead records them with `tools/usage.py record <ID> --tokens N`.

- **Specialists:** the lead hands each task to a fresh `subagent` whose first calls are `pl_role` and `pl_task`. The role's instructions join the child's prompt; its model hint (`fast`, `standard`, `strong`) picks the model where `list_subagent_models` allows. A role only narrows: it never grants lead or widens a scope.
- **Gates:** `pl_gate` runs `tools/gate.py` in the harness shell, passes the slot and locks the task's `exclusive` resources. A busy resource reports BUSY; `infra | busy | timeout` is never evidence.
- **Stop condition:** `create_goal` "gates green for Mxx" with a small `max_goal_rounds`. Only the owner resumes a blocked goal.
- **Runtime:** ports, database and bucket from `.polier-slot` (`tools/slot.py show`). Never stop a process you did not start; the plugin warns once per turn.
- **Reviewer:** a fresh subagent in `reviewer` mode with the `pl_review` packet; sees only diff, criteria and records; writes only under `reviews/`; binds with `pl_task` without taking the builder's claim.

**M — lead + 2–3 workers.** Workers, best option first: `spawn_teammate` (Agent Teams; inherits the lead's model), a fresh `subagent` per task continued with `send_message`, or sessions the owner starts. One worktree per task (`worktrees: required`). `wait_agent` instead of polling; `interrupt_agent` for a worker that leaves its scope. At most 3 workers, never with overlapping scopes.

**L — team + integrator.** As M, plus an integration branch with its own merge task and CI. A task with `package` writes inside it; `boundaries` and `contracts` are its gates. `tools/release_check.py` is the `release-clean` gate, `tools/smoke.py` runs after every deploy. Review lenses (correctness, security/data/tests) run in parallel with `workflow` and merge into one `reviews/Mxx.md`.

**Agent Teams board.** `board.json` stays the source of truth. Mirror each task with `team_task_create(subject="M03 — <title>", write_scopes=[…], blocked_by=[…])`; update with compare-and-set (`team_task_get`, then `team_task_update`). A team task and a Polier claim are two views of one assignment: take the claim before the worker starts. `complete` only after verification, review and merge.

## 4. Worktrees and slots

```bash
python3 <package>/tools/worktree.py start M03 --base main   # lead: branch task/M03, slot, claim
python3 <package>/tools/slot.py show                        # worker, inside the worktree
python3 <package>/tools/worktree.py finish M03              # lead, after the merge
```

`start` runs `git worktree add ../<repo>-M03 -b task/M03 <base>`, acquires a slot, takes the claim and sets the task's `worktree`. `finish` refuses a dirty checkout, then releases claim and slot and removes the checkout. With the Git Worktrees bundle, `create_worktree` makes the branch under `.agents/worktrees/<name>`; take slot and claim yourself (`slot.py acquire`, `claim.py take M03 --harness dsh --session …`).

Slots run `1 … slots-1` (0 is the owner's checkout); ports are `port_base + port_stride·N + offset`. Polier creates no databases; the project's `tools/dev/setup` reads `.polier-slot`. The stop check reports changes inside another live claim's scope as "foreign changes" without blaming the current session.

Rules: one worktree per task; rebase and rerun the gates before a merge, rerun them after; semantic conflicts are the owner's; two failed merges → `blocked`.

Shared runtime files (written by the tools, read by every session): `.polier-slot`, `<git-common-dir>/polier/slots.json`, `claims/<task>.json`, `locks/<resource>.lock`. Committed records: `policy.json`, `runs/<ID>.json`, `reviews/approvals/AP-NNN.json`, `factory.json`, `docs/factory.md`.

## 5. Models and context

- Cheaper models for recon, research and test design; the strongest available for critic and reviewer.
- Every agent gets its brief, the STATUS excerpt and its context pack, never other briefs or the whole history. At L: root files plus the package's own files.
- Budgets: worker ≤ 30k input, reviewer ≤ 15k, lead ≤ 30k. Over budget → split the task or trim the context.
- Children return structured results with evidence, not narratives.

## 6. Approvals and security

- Closing a station, lead mode, `off` mode and every high-risk action (`new_dependency`, `release`, …) are approval prompts; the record lands in `factory.json` or `reviews/approvals/`. A record is cooperative evidence: whoever can write the file can forge it.
- Stepping back to worker or reviewer needs no approval.
- Releases are a human or CI action: no tag, publish or deploy from an agent session.

## 7. Installing and configuring

`dsh plugin --profile <name> add github:atshv/polier` (or a local path), then restart DSH or enable it under **Plugins**. Remove with `dsh plugin --profile <name> remove dsh-polier`. The bundle patch (`cordis.patch.yml`) inserts one row:

| Key | Default | Meaning |
|---|---|---|
| `enforce` | `deny` | `deny` blocks, `ask` turns a denial into an approval prompt, `off` disables the guard |
| `stopCheck`, `maxStopReminders` | `true`, `2` | compare the git diff with the scope before a worker's turn ends |
| `python` | `python3` (`python` on Windows) | interpreter for the package tools and the guard |
| `owner` | `owner` | name written into records the owner answers |
| `context` | `true` | the `<polier>` block and the guide |
| `skill` | `true` | register the `polier` skill |

Which tasks bind a session: the one bound with `pl_task`, else the `in_progress` task whose `worktree` contains the session folder, else every `in_progress` task. Without a running task or in a lead session, only the policy rules apply. In a worktree, bind the session with `pl_task`. Claims are released when the session ends.

Limits (details in `docs/guard-limits.md`): the guard sees the guarded file tools and `bash` command lines; files a `bash` command writes are caught afterwards by the stop check and the review. Each guarded call starts one short Python process. Roles reset to `worker` on restart; claims expire after 10 minutes without a heartbeat.

## 8. Ralph, workflows, teams

| Tool | Use in Polier |
|---|---|
| `ralph` | Only when the owner asks for fresh-agent iteration on one task; Polier's gates, review and `pl_state` are what count. |
| `workflow` | Broad read-only checks (critics, audits, recon), never day-to-day tasks. |
| Agent Teams | Workers for M/L when enabled. |
| `schedule_*`, `session_search`, `run_code` | Not needed: board, line and gates are the record. |

## 9. Anti-patterns

| Anti-pattern | Better |
|---|---|
| Asking the owner to type a command | call the tool |
| A chat "yes" as approval | `pl_mode`, `pl_factory advance`, `pl_approval` |
| `pl_status` every step | read the `<polier>` block |
| Ticking an item to pass a station | evidence: a file or a done task |
| `spawn_teammate` for planning | subagents for critique |
| Assuming Agent Teams or worktrees exist | check in station 1 |
| Planning or merging in a worker session | `pl_mode lead` |
| Two sessions on one task | `pl_task` claims; a live claim fails |
| Retrying a BUSY gate in parallel | wait or rerun alone |
| Hard-coded ports or database names | `.polier-slot` |
| "tests passed" as evidence | the record path from `pl_gate` |
| Retrying above `max_attempts_per_task` | `pl_state` refuses; record `blocked`, escalate |

## Sources (checked 2026-11-09)

- [Tool catalog](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/tool-catalog.md)
- [Workflow](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/workflow.md)
- [Plan mode](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/plan.md)
- [Goal](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/goal.md)
- [Skills](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/skills.md)
- [Worktrees](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/worktrees.md)
- [Agent Teams](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/agent-team.md)
- npm: `@deepseek-ai/dsh-system-prompt`, `dsh-user-approval`, `dsh-goal`, `dsh-tool-goal`, `dsh-tool-subagent`, `dsh-tool-ralph` 0.2.2-rc.1
