# DeepSeek Harness: How Polier Runs Inside It

Polier is built for the DeepSeek Harness (DSH). This file maps each station of `prompt/generator.md`, and the execution of the generated project, to the DSH seam or tool that does it best.

> **Verified (2026-11-09)** against the published DSH packages `@deepseek-ai/dsh` 0.2.2-rc.1 (READMEs and type declarations of `dsh-system-prompt`, `dsh-tools`, `dsh-user-approval`, `dsh-goal`, `dsh-tool-goal`, `dsh-tool-subagent`, `dsh-tool-ralph`, `dsh-workflow`) and this package's `plugin/`, `core/` and `tools/`. Details the packages do not state are marked `[UNVERIFIED]`.

## 0. No commands: what the plugin gives every session

Every tool, parameter and the guide text are listed in [`docs/tools.md`](../docs/tools.md), generated from the plugin code.

| Seam | What Polier does with it |
|---|---|
| Runtime context (`ctx.systemPrompt.context`) | A live `<polier>` block in every model step: project, role, the factory station with its open items, the running task with scope and gates, ready tasks, policy limits, pending approvals and the next sensible move. Empty outside a Polier project. |
| System prompt section (`ctx.systemPrompt.section`) | A short guide in sessions inside a Polier project: map plain language to tools, records only through tools, decisions only through approval prompts, evidence instead of ticks. |
| Approval service (`ctx.approval`) | Every human decision is a real DSH approval prompt: `pl_mode lead`/`off`, `pl_factory advance` (closing a station) and `pl_approval` (Polier approval records). The answer is logged in the session and written into the record. Without an approval answerer (headless, CI) the prompt fails closed. |
| Tool guard (`ctx.tools.guard`) and `tools/pre-execute` | The write guard, the policy command guard, claim heartbeats and the kill warning. |
| `agent/turn-stopping` | The stop check: git diff against the task scope, sent back to the agent. |
| Skills (`ctx.skills`) | The `polier` skill, with its files resolved inside the package. |

The human talks plainly ("weiter", "what is missing?", "close the station", "take M03"); the agent calls the matching tool. Nobody types a slash command or a Python line. The Python tools in `tools/` stay the single implementation underneath and the way to work headless.

## 1. Before you start: what is available

DSH composes its tools from packages, so not every session has every tool. In phase A1, look at the session's tool list and use the fallback column for anything missing.

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

- **`AGENTS.md` is loaded automatically.** DSH injects `~/.dsh/AGENTS.md`, `~/.agents/AGENTS.md` and every `AGENTS.md` from the project root down to the working directory into each session. The generated `AGENTS.md` therefore reaches every agent without being pasted, which makes its 300–400-word budget even more important. At profile L the nested `<package>/AGENTS.md` is loaded the same way. Context packs do not need to list either.
- **Plan mode is guidance, not enforcement.** It changes the prompt only. What an agent may write or run is decided by the sandbox and the approval policy. If a gate command is blocked there, the human runs it and pastes the output.

Runtime and orchestration state are not a harness feature; they are files shared by every worktree of the repo, written by this package's tools:

| File | Written by | Read by |
|---|---|---|
| `.polier-slot` | `tools/slot.py acquire` (also `tools/worktree.py start`) | the session, `tools/dev/setup`, gates and servers |
| `<git-common-dir>/polier/slots.json` | `tools/slot.py` | `slot.py list` |
| `<git-common-dir>/polier/claims/<task>.json` | `tools/claim.py` (`pl_task` in the plugin) | every session, `pl_status` |
| `<git-common-dir>/polier/locks/<resource>.lock` | `tools/gate.py --exclusive` (`pl_gate`) | every harness |
| `policy.json` | the generator, later the owner (committed) | the guard, `tools/state.py`, `dispatch.py`, `audit.py`, `check.py`, `pl_next` |
| `runs/<ID>.json` | `tools/state.py`; gate events by `tools/gate.py` (committed) | `tools/state.py`, `dispatch.py`, `audit.py`, `check.py`, `pl_state`, `pl_next` |
| `reviews/approvals/AP-NNN.json` | `tools/approve.py`, `pl_approval` (committed) | the guard, `tools/state.py`, `audit.py`, `check.py` |
| `factory.json`, `docs/factory.md` | `tools/factory.py`, `pl_factory` (committed) | the live context, `check.py`, `render_status.py` |

## 2. Running the generator: phase → tool

| Phase | Use | How | Fallback |
|---|---|---|---|
| all | `todo_write` | One item per phase (A, B, C+D, E, F, G, H, I); mark each when its approval or check is done. | none needed |
| A1 tool check | session tool list | Fill in section 1 for this session and name the fallbacks in the profile proposal. With the plugin the `pl_*` tools and the `<polier>` block exist; without it, call `tools/*.py` with `bash`. | ask the user |
| A4 start the line | `pl_factory` init | Shows the owner the planned line (items per station) in an approval prompt and writes `factory.json` only on yes; then `pl_factory` records items and `pl_factory advance` asks the owner to close the station. Full parameters: `docs/tools.md`. | `tools/factory.py init` |
| every station | `create_goal` | When the human asks to finish a station, a goal such as "Close Polier station concept: resolve every open item with evidence"; the `<polier>` block shows what is left in each round. | work turn by turn |
| A2 interview | `ask_user_question` | Max. 10 questions per call. Give `options` where the answer space is closed (mode, profile, platform, yes/no), with the recommended option first; free text otherwise. | questions in chat |
| A, B, F facts | `web_search`, `web_fetch` | Check library versions, APIs and formats before writing them down. Record the answer with `tools/research.py note` and versions with `tools/research.py versions --lookup --write`; briefs link the note. | `[UNVERIFIED]` + ask |
| B recon | `subagent` or `workflow` | Read-only children, one per top-level area of the repo, each returning facts with file paths. Use a cheaper model if `list_subagent_models` offers one. | main session reads the repo |
| C+D approval | `/plan` + `exit_plan_mode` | Plan = architecture + artifact map + DAG table + Mermaid, starting with a `#` heading. At L include the package map, stages and contract list. "Keep planning" returns the user's feedback: revise and resubmit. Approved = the S joint yes. | show in chat, wait for "yes" |
| C, D critics (M/L) | `workflow` | Run architecture critic, scope critique and test design as parallel fresh agents; each returns findings only. At L one of them checks package boundaries and contract versions. | three sequential `subagent` calls |
| E approval (M/L) | `exit_plan_mode` | Roles and protocol as a second plan. | chat |
| H cold start + rubric | `subagent`, then `send_message` | Step 1 to a fresh child with the four cold-start files (L: plus the package `ARCHITECTURE.md`/`AGENTS.md`); step 2 to the same child via `send_message`. | second fresh `subagent` (fallback rule in `prompt/generator.md`) |
| H lint | `pl_check` | `tools/check.py` including the factory line; at L also `tools/boundaries.py .` and `tools/contracts.py check` with `bash`; `tools/audit.py .` (exit 0) and `pl_next` (no conflicts). | `bash` |
| I handoff | `present` | Exactly four files: `ARCHITECTURE.md`, `AGENTS.md`, `STATUS.md`, `tasks/M01.md`. The rest goes into the file tree in chat. | file tree in chat |

Subagents and `workflow` only read, research and criticise. `spawn_teammate` and the team board are for executing the project, not for designing it.

## 3. Executing the generated project

### The task loop

A 1.1 project moves through the same checkpoints in every profile. The lead runs the transitions; a worker session reads the state and reports.

| Step | Lead session | Worker session |
|---|---|---|
| choose | `pl_next` (waves, blocked tasks, conflicts) | — |
| start | `pl_state` M03 → `in_progress` | `pl_task` M03 (binds and claims) |
| build | — | code inside the scope, `pl_gate` per gate, `pl_scope_check` |
| check | `pl_state` → `verifying`, then `review` | — |
| review | fresh reviewer subagent (`pl_mode reviewer`) writes `reviews/M03.md` | — |
| close | `pl_state` → `done` or `rework`; `pl_factory done` for the linked items | — |

STATUS.md and docs/factory.md regenerate after every recorded change. Status changes are lead-only; reading works everywhere. Checkpoints, attempts, rounds, approvals, the token budget and the behaviour without `policy.json` are described once, in `prompt/orchestration.md`. DSH does not hand its token counts to plugins, so with a budget the lead records them per task with `python3 <package>/tools/usage.py record <ID> --tokens N --session <name>`.

### S — one writer, one reviewer

- One session per task (new chat or `/clear`). The agent reads `ARCHITECTURE.md`, `STATUS.md`, `docs/orchestration.md`, `docs/module-map.md` and `tasks/Mxx.md`; `AGENTS.md` is already loaded and the `<polier>` block shows the task, its scope and its gates.
- **Before the worker starts:** the lead (`pl_mode lead`, approved by the owner) creates the worktree when the board wants one — `python3 <package>/tools/worktree.py start M03` (branch, slot and claim in one step) — and records `in_progress` with `pl_state`. The worker binds with `pl_task`, which takes or refreshes its claim; every tool call refreshes the heartbeat at most once a minute. A live claim of another session makes `pl_task` fail and names the holder.
- **Runtime resources:** the worktree keeps its ports, test database and bucket in `.polier-slot`; `slot.py show` prints them. Never `kill`, `pkill` or `killall` a process you did not start — the plugin sends one advisory message per turn, it does not block.
- **Stop condition as a goal:** `create_goal` with "gates green for Mxx" as `objective` and a small `max_goal_rounds` derived from the brief's stop rule. DSH counts goal rounds as continuation turns, so the cap is an upper bound, not the rework-round count itself. When the goal is blocked or paused, only the human can resume it.
- **Gates:** `pl_gate` with the gate name from the board; it runs `tools/gate.py` through the harness shell, passes `--slot` from `.polier-slot`, locks every resource in the task's `exclusive` list automatically and returns the record path, which is the evidence. `lock_wait_s` defaults to 0, so a busy resource reports BUSY at once; raise it to wait for the holder. A record with `result: infra | busy | timeout` is not evidence — rerun the gate alone. Without the plugin, run `tools/gate.py` with `bash` (long gates with `run_in_background`, then `job_output`).
- **Specialists:** every build task names a role (`docs/roles.md`). The lead delegates it to a fresh `subagent` whose first steps are `pl_role` with that role and `pl_task` with the task; the role's instructions join the child's system prompt, and its model hint (`fast`, `standard`, `strong`) picks the child's model where the subagent tool allows a choice.
- **Reviewer:** a fresh `subagent` (or session) in the `reviewer` role that sees only the diff, the criteria and the gate records, never the author's session. The role switches it to reviewer mode (no approval needed: a role only narrows) and it writes only under `reviews/`.

### M — lead + 2–3 workers

- **Lead** = main session. Writes no feature code.
- **Workers**, best option first:
  1. Agent Teams enabled: `spawn_teammate` per worker (durable, own context). It has no model parameter; a teammate inherits the lead's model.
  2. Otherwise: one `subagent` per task with a fresh context, continued with `send_message`.
  3. Otherwise: several sessions started by the human.
- **One checkout per task:** on a 1.0 board the default is `worktrees: required` at M/L (a 0.9 board stays on `recommended`). `worktree.py start <ID>` creates `../<repo>-<ID>` on branch `task/<ID>`, acquires a slot and takes the claim; `worktree.py finish <ID>` refuses a dirty checkout and otherwise releases claim and slot and removes the worktree. A worker write in the main checkout for a task with a worktree is denied with "work in <worktree path>".
- **Coordination:** `wait_agent` for the next status, message or task change instead of polling. `interrupt_agent` to stop a worker that leaves its scope. `pl_status` in any session shows the live claims of the repo, so two workers never take the same task.
- **Board:** `team_task_create` with `write_scopes` and `blocked_by` (section 4). `board.json` stays the portable source of truth.
- **Verifier** = Bash gates, no LLM opinion. **Reviewer** = read-only `subagent`, without the author's reasoning.
- At most 3 workers at a time; no two with overlapping scopes. The Agent Teams profile also caps the team size (`maxMembers`).

### L — team + integrator

- As M, plus an integration branch with its own merge task, CI/quality gates, runbook and observability.
- **One package owner per stage:** a task with `package` writes inside that package; `boundaries` (import rules) and `contracts` (schema versions) are its gates. Two packages in parallel only with disjoint `write_scopes` and no shared decision.
- **Release path:** `tools/release_check.py` is the `release-clean` gate; agents never tag or publish. Smoke after every deploy with `tools/smoke.py` (see `templates/releasing.md` › Release check).
- **Review lenses with `workflow`:** run correctness/acceptance and security/data/test quality as parallel reviewers over the same diff; merge their findings into one `reviews/Mxx.md`.
- `workflow` also fits broad, independent checks (audits across many files). It is not for day-to-day tasks.

## 4. Board mapping: `board.json` → team tasks

`board.json` is portable and stays the source of truth. With Agent Teams, also create each task on the team board:

```text
team_task_create(
  subject="M03 — <title>",
  description="<goal, acceptance, scope, gates, context pack, exclusive resources>",
  write_scopes=["src/...", "tests/..."],
  blocked_by=["<team task ID of M02>"]
)
```

- `write_scopes` must be disjoint; `blocked_by` maps `depends_on`; a stage's `exit_gates` and `owner_decision` map to the team task's completion criteria.
- Updates use compare-and-set: read with `team_task_get`, then `team_task_update`. A rejected update means someone else changed the task; read again, do not overwrite.
- The lead does not claim tasks; it assigns them or allows self-claim. A team task and a live Polier claim are two views of the same assignment: before a worker starts, create the claim (`worktree.py start` or `claim.py take`).
- `complete` only after verification, review and merge.
- Generate `STATUS.md` from `board.json`; do not maintain it in parallel. Claims are runtime state and never written into `board.json`.

## 5. Worktrees and branches

**Prerequisite:** a git repo with `main`, `.gitignore` and an initial commit.

**The package helper (preferred):**

```bash
# lead, from the main checkout, before the task starts
python3 <package>/tools/worktree.py start M03 --base main

# worker, inside the printed worktree
python3 <package>/tools/slot.py show
python3 <package>/tools/claim.py list

# lead, after the merge: refuses a dirty checkout, releases claim and slot
python3 <package>/tools/worktree.py finish M03
```

`start` runs `git worktree add ../<repo>-M03 -b task/M03 <base>`, acquires the worktree's runtime slot, takes the task's claim and writes the `worktree` field of that task. `finish` refuses while `git status` in the worktree is not empty, releases the claim and the slot, removes the checkout and clears the field.

**With the Git Worktrees bundle:** `create_worktree(name="task/M03", from="main")` creates the branch and a checkout under `.agents/worktrees/<name>`. It copies no uncommitted files, and it neither merges nor removes anything; take a slot and a claim yourself.

**Without either helper:**

```bash
# per task, before the start
git worktree add ../wt-M03 -b task/M03
python3 <package>/tools/slot.py acquire        # in the new worktree
python3 <package>/tools/claim.py take M03 --harness dsh --session "$SESSION" --worktree "$PWD"

# after the work, inside the worktree
git add -A && git commit -m "M03: <title>"

# the lead merges and cleans up
git checkout main
git merge --no-ff task/M03
python3 <package>/tools/slot.py release        # in the worktree
python3 <package>/tools/claim.py release M03
git worktree remove <worktree path>
```

**Runtime slots.** `slot.py acquire` picks the lowest free slot `1 … slots-1` (slot 0 is the owner's main checkout and is never registered), writes `.polier-slot` with the ports, `db_name` and `bucket`, and registers it in `<git-common-dir>/polier/slots.json`. Ports are `port_base + port_stride·N + service offset`; defaults are 3 slots, base 4000, stride 100. `slot.py list` marks slots whose worktree folder is gone as stale; `acquire --reclaim-stale` reuses them. Polier creates no databases or buckets — the project's `tools/dev/setup` reads `.polier-slot`. `.polier-slot` is gitignored, and slot 0's data is never touched from a worktree.

**Foreign changes.** The stop check compares the working tree with the task. A changed file that is outside the current task's scope but inside the `scope_write` of a task with another live claim is reported as "foreign changes (task X, harness Y)" and does not block the current session.

Rules:

- One worktree per task, not per agent.
- Before the merge: rebase onto the integration branch, run the gates again.
- After the merge: run the gates again; a green task branch does not guarantee a green main.
- Semantic conflicts are decided by the human, not the agent.
- After two failed merge attempts: `blocked`.

## 6. Models, context and tokens

- **Models:** `list_subagent_models` shows what is available. Cheaper models for recon, research and test design; the strongest available model for the critic and the reviewer. Without model selection, every child uses the session's model.
- Every agent gets its task brief, the STATUS excerpt and the files named in its context pack. **Not:** other briefs, the whole chat history, all docs. At L the context pack is root files plus the package's own files.
- Budgets: worker ≤ 30k input, reviewer ≤ 15k, lead ≤ 30k. Over budget → split the task or trim the context.
- Children return structured results + evidence, not narratives. The lead never summarises a worker's decision without naming the file/ADR.

## 7. Approvals and security

- Station decisions (closing idea, concept, design, architecture, plan …) are `pl_factory advance`: the owner answers a DSH approval prompt and the station records `approved_by`.
- Plan reviews still fit `/plan` + `exit_plan_mode` for the C+D draft; single questions (scope, budget, stage `continue`/`stop`) fit `ask_user_question`.
- High-risk actions in a running project are approval records, not chat: `pl_approval` writes `reviews/approvals/AP-NNN.json`, opens the prompt and records granted or denied. The guard and `tools/state.py` read the record; a granted record does not expire. The record is cooperative evidence — whoever can write the file can forge it.
- Lead mode is a decision too: `pl_mode lead` opens a prompt; stepping back to worker or reviewer does not.
- Plan mode does not block writes; the sandbox, the approval policy and the Polier guard do. Keep the session's permissions to the working folder and the task's scope.
- Releases are a human/CI action: no tag, publish or deploy from an agent session.
- All other rules: `prompt/generator.md` › rules.

## 8. Installing and configuring the plugin

`dsh plugin --profile <name> add github:atshv/polier` (or a local path), then restart DSH or enable it under **Plugins**. Remove with `dsh plugin --profile <name> remove dsh-polier`. The bundle patch (`cordis.patch.yml`, referenced by `package.json` → `dsh.bundle.patch`) inserts one row; its config:

| Key | Default | Meaning |
|---|---|---|
| `enforce` | `deny` | `deny` blocks out-of-scope writes, `ask` turns them into an approval prompt, `off` disables the guard |
| `stopCheck`, `maxStopReminders` | `true`, `2` | compare the git diff with the scope before a worker's turn ends |
| `python` | `python3` (`python` on Windows) | interpreter for the package tools |
| `owner` | `owner` | name written into records the owner answers in a prompt |
| `context` | `true` | the `<polier>` block and the guide |
| `skill` | `true` | register the `polier` skill |

Which tasks bind a session: the one bound with `pl_task`, else the `in_progress` task whose `worktree` contains the session directory, else every `in_progress` task (a path must fit one of their scopes). No task in progress, no board, or a lead session: the guard stays out of the way. In a worktree the session finds the worktree's own copy of `board.json`, where the task may still be `pending`; bind the session with `pl_task`, which also claims it. Claims are released when the session is disposed.

Limits: the guard sees only the guarded file tools; `bash` writes are caught afterwards by the stop check and the review. Roles are in memory and reset to `worker` on restart; claims live in files and expire by heartbeat (10 minutes). The kill warning is advisory. Gate commands run through `ctx.shell` with the session's sandbox policy on macOS and Linux; on Windows `gate.py` starts them directly. A reviewer may write only under `reviews/`; its `bash` is not limited, so a read-only sandbox is still the stronger option.

## 9. Ralph, workflows and teams

| Tool | Use in Polier |
|---|---|
| `ralph` | Only when the human asks for fresh-agent iteration on one task. Its round reports are not verified by DSH; Polier's gates (`pl_gate`), review and `pl_state` checkpoints are what count. |
| `workflow` | Broad read-only checks (critics, audits, recon), never day-to-day tasks. |
| Agent Teams | Workers for M/L when the profile enables it (section 3). |
| `schedule_*`, `session_search`, `run_code` | Not needed: the board, the line and the gates are the record. |

## 10. DSH anti-patterns

| Anti-pattern | Better |
|---|---|
| Asking the human to type a command | call the tool; the `<polier>` block says which |
| Treating a chat "yes" as an approval | `pl_mode`, `pl_factory advance`, `pl_approval` open a real prompt |
| Calling `pl_status` every step | read the `<polier>` block |
| Ticking a factory item to get past a station | evidence: a file or a done task; must items are never deferred |
| `spawn_teammate` for planning | subagents for critique |
| Assuming Agent Teams or worktrees exist | check in phase A1, use the fallback |
| Pasting `AGENTS.md` into prompts | it is already loaded; keep it short |
| More teammates than parallel tasks | max. 3 workers, M/L only |
| Planning or merging in a worker session | `pl_mode lead`, approved by the owner |
| Two sessions on one task | `pl_task` claims; a live claim fails |
| Running an exclusive gate in parallel and retrying | wait for the lock or rerun alone; a BUSY record is not evidence |
| `pkill` a dev server another session started | stop only what you started; use your slot's ports |
| Hard-coding ports, database or bucket names | read `.polier-slot` |
| Publishing or tagging from a worktree | releases run in CI from tags |
| Free-text evidence ("tests passed") | the record path from `pl_gate` |
| Editing `board.json`, `factory.json`, `runs/` or `reviews/approvals/` | the tools write them and run the checks |
| Retrying a task above `max_attempts_per_task` | `pl_state` refuses; record `blocked` and escalate |

## Sources (checked 2026-11-09)

- [Tool catalog](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/tool-catalog.md)
- [Workflow](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/workflow.md)
- [Plan mode](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/plan.md)
- [Goal](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/goal.md)
- [Skills](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/skills.md)
- [Worktrees](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/worktrees.md)
- [Agent Teams](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/agent-team.md)
- [Model selection in Agent Teams (discussion)](https://github.com/deepseek-ai/deepseek-harness/discussions/6985)
- npm: `@deepseek-ai/dsh-system-prompt`, `dsh-user-approval`, `dsh-goal`, `dsh-tool-goal`, `dsh-tool-subagent`, `dsh-tool-ralph` 0.2.2-rc.1 (package READMEs and `lib/types`)
