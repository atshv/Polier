# DeepSeek Harness: Using Its Strengths

Maps each phase of `prompt/generator.md`, and the execution of the generated project, to the DeepSeek Harness (DSH) tool that does it best, with a fallback.

> **Verified (2026-10-18)** against the DSH docs (`docs/tool-catalog.md` and `docs/subsystems/` on `master`) and the installed app 0.2.1-rc.2, whose `app.asar` contains every tool name used here. Details the docs do not state are marked `[UNVERIFIED]`.

## 1. Before you start: what is available

DSH composes its tools from packages, so not every session has every tool. In phase 0.1, look at the session's tool list and use the fallback column for anything missing.

| Capability | Tools | Availability |
|---|---|---|
| Files, shell, search | `read`, `write`, `edit`, `bash`, `glob`, `grep` | standard |
| Background jobs | `bash` with `run_in_background`, `job_list`, `job_output`, `job_kill` | needs the job registry |
| Structured questions | `ask_user_question` | `dsh-tool-ask-user` |
| Plan mode | `/plan`, `exit_plan_mode` | optional `dsh-plan-mode` package |
| Checklist | `todo_write` | `dsh-tool-todo` |
| Web research | `web_search`, `web_fetch` | `dsh-tool-web` |
| Subagents | `subagent`, `send_message`, `interrupt_agent`, `list_subagent_models` | `dsh-tool-subagent`; model choice only when selection is on |
| Orchestration | `workflow` | `dsh-tool-workflow` |
| Long objectives | `create_goal`, `get_goal`, `update_goal` | `dsh-tool-goal` |
| Deliverables | `present` (max. 4 files) | `dsh-tool-present` |
| Agent Teams | `spawn_teammate`, `wait_agent`, `team_task_create/get/list/update` | **experimental**, off in the shipped `dsh-base` bundle; enabled by the Agent Teams profile |
| Worktrees | `create_worktree` | **experimental**, "Git Worktrees" bundle, off by default |
| Skills | `skill` | `dsh-tool-skill` |

Two facts that change how the generator works in DSH:

- **`AGENTS.md` is loaded automatically.** DSH injects `~/.dsh/AGENTS.md`, `~/.agents/AGENTS.md` and every `AGENTS.md` from the project root down to the working directory into each session. The generated `AGENTS.md` therefore reaches every agent without being pasted, which makes its 400-word budget even more important. Context packs do not need to list it.
- **Plan mode is guidance, not enforcement.** It changes the prompt only. What an agent may write or run is decided by the sandbox and the approval policy. If a gate command is blocked there, the human runs it and pastes the output.

## 2. Running the generator: phase → tool

| Phase | Use | How | Fallback |
|---|---|---|---|
| all | `todo_write` | One item per phase (0, B, C+D, E, F, G, H, I); mark each when its approval or check is done. | none needed |
| 0.1 tool check | session tool list | Fill in section 1 for this session and name the fallbacks in the profile proposal. | ask the user |
| 0.2 interview | `ask_user_question` | Max. 10 questions per call. Give `options` where the answer space is closed (mode, profile, platform, yes/no), with the recommended option first; free text otherwise. | questions in chat |
| 0, B, F facts | `web_search`, `web_fetch` | Check library versions, APIs and formats before writing them down. Put source URL and date into the brief's pitfalls. | `[UNVERIFIED]` + ask |
| B recon | `subagent` or `workflow` | Read-only children, one per top-level area of the repo, each returning facts with file paths. Use a cheaper model if `list_subagent_models` offers one. | main session reads the repo |
| C+D approval | `/plan` + `exit_plan_mode` | Plan = architecture + artifact map + DAG table + Mermaid, starting with a `#` heading. "Keep planning" returns the user's feedback: revise and resubmit. Approved = the S joint yes. | show in chat, wait for "yes" |
| C, D critics (M/L) | `workflow` | Run architecture critic, scope critique and test design as parallel fresh agents; each returns findings only. | three sequential `subagent` calls |
| E approval (M/L) | `exit_plan_mode` | Roles and protocol as a second plan. | chat |
| H cold start + rubric | `subagent`, then `send_message` | Step 1 to a fresh child with the four cold-start files; step 2 to the same child via `send_message`. | second fresh `subagent` (fallback rule in `prompt/generator.md`) |
| H lint | `bash` | `python3 <package>/tools/check.py .`, where `<package>` is `.generator` or the skill folder | none needed |
| I handoff | `present` | Exactly four files: `ARCHITECTURE.md`, `AGENTS.md`, `STATUS.md`, `tasks/M01.md`. The rest goes into the file tree in chat. | file tree in chat |

Subagents and `workflow` only read, research and criticise. `spawn_teammate` and the team board are for executing the project, not for designing it.

## 3. Executing the generated project

### S — one writer, one reviewer

- One session per task (new chat or `/clear`). The agent reads `ARCHITECTURE.md`, `STATUS.md`, `docs/module-map.md` and `tasks/Mxx.md`; `AGENTS.md` is already loaded. With the plugin (section 8), `pg_status` shows the running task, its scope and the handoffs.
- **Before the worker starts:** set the task to `in_progress` in `board.json` from a lead session (`/pg lead`). From then on the plugin limits every worker session to that task's scope.
- **Stop condition as a goal:** `create_goal` with "gates green for Mxx" as `objective` and a small `max_goal_rounds` derived from the brief's stop rule. DSH counts goal rounds as continuation turns, so the cap is an upper bound, not the rework-round count itself. When the goal is blocked or paused, only the human can resume it.
- **Gates:** `pg_gate` with the gate name from the board; it runs `tools/gate.py` through the harness shell and returns the record path, which is the evidence. Without the plugin, run `tools/gate.py` with `bash` (long gates with `run_in_background`, then `job_output`).
- **Reviewer:** a fresh session (`/pg reviewer`) or `subagent` that sees only the diff, the criteria and the gate records, never the author's session. A subagent starts as a worker; it is limited to the task scope, not to `reviews/`.

### M — lead + 2–3 workers

- **Lead** = main session. Writes no feature code.
- **Workers**, best option first:
  1. Agent Teams enabled: `spawn_teammate` per worker (durable, own context). It has no model parameter; a teammate inherits the lead's model.
  2. Otherwise: one `subagent` per task with a fresh context, continued with `send_message`.
  3. Otherwise: several sessions started by the human.
- **Coordination:** `wait_agent` for the next status, message or task change, instead of polling. `interrupt_agent` to stop a worker that leaves its scope.
- **Board:** `team_task_create` with `write_scopes` and `blocked_by` (section 4). `board.json` stays the portable source of truth.
- **Verifier** = Bash gates, no LLM opinion. **Reviewer** = read-only `subagent`, without the author's reasoning.
- At most 3 workers at a time; no two with overlapping scopes. The Agent Teams profile also caps the team size (`maxMembers`).

### L — team + integrator

- As M, plus an integration branch with its own merge task, CI/quality gates, runbook and observability.
- **Review lenses with `workflow`:** run correctness/acceptance and security/data/test quality as parallel reviewers over the same diff; merge their findings into one `reviews/Mxx.md`.
- `workflow` also fits broad, independent checks (audits across many files). It is not for day-to-day tasks.

## 4. Board mapping: `board.json` → team tasks

`board.json` is portable and stays the source of truth. With Agent Teams, also create each task on the team board:

```text
team_task_create(
  subject="M03 — <title>",
  description="<goal, acceptance, scope, gates, context pack>",
  write_scopes=["src/...", "tests/..."],
  blocked_by=["<team task ID of M02>"]
)
```

- `write_scopes` must be disjoint; `blocked_by` maps `depends_on`.
- Updates use compare-and-set: read with `team_task_get`, then `team_task_update`. A rejected update means someone else changed the task; read again, do not overwrite.
- The lead does not claim tasks; it assigns them or allows self-claim.
- `complete` only after verification, review and merge.
- Generate `STATUS.md` from `board.json`; do not maintain it in parallel.

## 5. Worktrees and branches

**Prerequisite:** a git repo with `main`, `.gitignore` and an initial commit.

**With the Git Worktrees bundle:** `create_worktree(name="task/M03", from="main")` creates the branch and a checkout under `.agents/worktrees/<name>`. It copies no uncommitted files, and it neither merges nor removes anything.

**Without it**, or for merge and cleanup in both cases:

```bash
# per task, before the start (only without create_worktree)
git worktree add ../wt-M03 -b task/M03

# after the work, inside the worktree
git add -A && git commit -m "M03: <title>"

# the lead merges and cleans up
git checkout main
git merge --no-ff task/M03
git worktree remove <worktree path>
```

Rules:

- One worktree per task, not per agent.
- Before the merge: rebase onto the integration branch, run the gates again.
- After the merge: run the gates again; a green task branch does not guarantee a green main.
- Semantic conflicts are decided by the human, not the agent.
- After two failed merge attempts: `blocked`.

## 6. Models, context and tokens

- **Models:** `list_subagent_models` shows what is available. Cheaper models for recon, research and test design; the strongest available model for the critic and the reviewer. Without model selection, every child uses the session's model.
- Every agent gets its task brief, the STATUS excerpt and the files named in its context pack. **Not:** other briefs, the whole chat history, all docs.
- Budgets: worker ≤ 30k input, reviewer ≤ 15k, lead ≤ 30k. Over budget → split the task or trim the context.
- Children return structured results + evidence, not narratives. The lead never summarises a worker's decision without naming the file/ADR.

## 7. Approvals and security

- Approvals: architecture + DAG and agent contract through `exit_plan_mode`; single decisions (merge conflict, budget, scope change) through `ask_user_question`.
- Plan mode does not block writes; the sandbox and approval policy do. Keep the session's permissions to the working folder and the task's scope.
- All other rules: `prompt/generator.md` › rules.

## 8. The generator as a DSH plugin

Install the package as a plugin: `dsh plugin --profile <name> add <path or package>`, then restart the harness. The bundle patch inserts one row; `package.json` → `dsh.bundle.patch` points to it. The plugin:

| Part | DSH seam | Effect |
|---|---|---|
| Skill | `ctx.skills.register` | `prompt-generator` in every session; relative paths resolve inside the package (`resourceBase`). |
| Write guard | `ctx.tools.guard` (monotonic; `enforce: ask` uses `tools/pre-execute` instead) | `write`, `edit`, `str_replace_editor` outside the running task's scope are denied. No other listener can turn the denial back into an allow. |
| Stop check | `agent/turn-stopping` + `agent.steer` | `tools/scope_check.py` against the git diff; violations go back to the agent, max. `maxStopReminders` per turn. |
| Tools | `ctx.tools.register` | `pg_status`, `pg_gate`, `pg_scope_check`, `pg_check`. |
| `/pg` | `ctx.commands.register` | Human-only role switch per session: `lead`, `worker` (default), `reviewer` (writes only under `reviews/`), `off`, `task <ID>`, `status`, `render`. |

Which tasks bind a session: the one pinned with `/pg task`, else the `in_progress` task whose `worktree` contains the session directory, else every `in_progress` task (a path must fit one of their scopes). No task in progress, no board, or a lead session: the guard stays out of the way. In a worktree the session finds the worktree's own copy of `board.json`, where the task may still be `pending`; bind the session with `/pg task <ID>`.

Limits: the guard sees only the guarded file tools; `bash` writes are caught afterwards by the stop check and the review. Roles are in memory and reset to `worker` on restart. Gate commands run through `ctx.shell` with the session's sandbox policy on macOS and Linux; on Windows `gate.py` starts them directly. A reviewer session (`/pg reviewer`) may write only under `reviews/`; its `bash` is not limited, so a read-only sandbox is still the stronger option.

Without the plugin, copy the package as a plain skill (`./install.sh`) to `~/.dsh/skills/prompt-generator/` (all projects) or `<project>/.dsh/skills/prompt-generator/` (one project, add it to `.gitignore`). Use one of the two, not both.

## 9. Deliberately not used

| Tool | Why not |
|---|---|
| `ralph` | Fresh-agent loop toward one objective; DSH allows it only when a human explicitly asks. It also bypasses the per-task review. |
| `schedule_*` | Reminders add nothing to the process. |
| `session_search` | Opt-in; the board and `STATUS.md` are the record. |
| `run_code` | Gates are shell commands; no need for a second execution path. |

## 10. DSH anti-patterns

| Anti-pattern | Better |
|---|---|
| `spawn_teammate` for the generator | subagents for critique |
| Assuming Agent Teams or worktrees exist | check in phase 0.1, use the fallback |
| Treating plan mode as a write lock | sandbox and approval policy |
| Pasting `AGENTS.md` into prompts | it is already loaded; keep it short |
| Polling teammates | `wait_agent` |
| More teammates than parallel tasks | max. 3 workers, M/L only |
| Planning or merging in a worker session | `/pg lead` first; the guard blocks board and brief edits |
| Free-text evidence ("tests passed") | the record path from `pg_gate` |

Plugin seams verified on 2026-10-23 against the published packages `@deepseek-ai/dsh-tools`, `dsh-commands` and `dsh-skill` 0.2.1-rc.3 (tests in `dsh/test/`).

## Sources (checked 2026-10-18)

- [Tool catalog](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/tool-catalog.md)
- [Workflow](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/workflow.md)
- [Plan mode](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/plan.md)
- [Goal](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/goal.md)
- [Skills](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/skills.md)
- [Worktrees](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/worktrees.md)
- [Agent Teams](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/agent-team.md)
- [Model selection in Agent Teams (discussion)](https://github.com/deepseek-ai/deepseek-harness/discussions/6985)
