# Polier

Plan an AI coding project before the first line of code, then keep the agents to the plan.

![version](https://img.shields.io/badge/version-1.1.0-blue?style=flat-square)
![license](https://img.shields.io/badge/license-MIT-green?style=flat-square)

A plugin for [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness), with hooks for Claude Code. It interviews you, writes a one-page architecture and a task plan, and after your approval sets up the project. While agents build, it blocks writes outside the current task, records test results as proof, and keeps a committed record of every attempt, approval and review round.

## Install

Requirements: DeepSeek Harness, git, Python 3.9+.

```bash
git clone https://github.com/atshv/polier.git
dsh plugin --profile web add ./polier
```

Use your own profile name instead of `web`, then restart the harness. Updating an existing install: `git pull` in the clone, run the same `add` command again and restart — one update is needed to get `tools/manifest.json` for drift detection.

**Claude Code:** run `./install.sh claude`, then add the hooks from [`adapters/claude-code/settings.example.json`](adapters/claude-code/settings.example.json) to `.claude/settings.json`. Details, roles and settings: [`adapters/claude-code/README.md`](adapters/claude-code/README.md).

## Start

Open a new session in an empty folder and write:

> Plan a new project: a command-line tool that stores my bookmarks locally and finds them again.

Polier asks its questions, shows the plan for approval, writes the project files and gives you the prompt for the first task. Once the project has a `policy.json`, every task moves through checkpoints instead of a hand-edited board.

## What's new in 1.1

1.1 turns the planner into an orchestration control plane. The board stays the plan; three new stores carry what the plan cannot:

- **Policy as code** — `policy.json`: limits (attempts per task, tasks in progress, review rounds), protected paths, dependency manifests that need an approval, denied and lead-only commands, and which done-checks are on. Checked mechanically; a project without the file keeps the 1.0 behaviour.
- **Checkpoints** — `tools/state.py` is the only writer of a task's status. It enforces gates before review, review before done, an open attempt before verifying, the attempt cap before another try, a free review round before a rework, and an approval before reopening a done task. A refused transition names what is missing and the command that records it.
- **Run records** — `runs/<ID>.json` per task: attempt counter, append-only gate/state/review/approval events, last result. Committed with the task; the audit trail a chat history cannot be.
- **Approvals** — `reviews/approvals/AP-NNN.json`: request, grant and deny records for new dependencies, protected paths, merges to the base branch, releases, reopening and forced transitions. The tools read every record, and the write guard checks the dependency approval before a manifest write.
- **Dispatch** — `tools/dispatch.py` turns the board into an execution plan: waves of tasks that may run in parallel, blocked tasks with the command that records the block, scope conflicts and pending approvals.
- **Audit** — `tools/audit.py` prints one compliance view per task: board status against the run record, attempts used, gates, review verdict, handoff, approvals. For a `done` task every check the policy turns on is an error; without `policy.json` the findings are warnings and the exit code stays 0.
- **The model on one page** — [`prompt/orchestration.md`](prompt/orchestration.md), and generated projects get `docs/orchestration.md`: the task loop, the stage loop, checkpoints, approvals, escalation and what is not covered.
- **Guard** — a dependency manifest is refused without a granted `new_dependency` approval, a protected path is refused to every session except a lead, denied commands are refused for every role and lead-only commands for worker and reviewer sessions (DeepSeek Harness and Claude Code).
- **STATUS.md** — still generated, never hand-edited, now from `board.json`, `runs/` and `policy.json`: a new "Orchestration" section shows limits, next wave, running attempts, blocked tasks with reasons and pending approvals. Run `tools/render_status.py` after every state change.
- **Compatibility** — 0.9 and 1.0 projects are unchanged: without `policy.json` the new checks warn instead of failing and the guard adds no policy denials. The transition table, the note rules and the `reopen_done`/`state_override` approvals still apply; the gate, review, attempt and concurrency checks degrade to warnings and the dependency approval is not checked. Board schema stays 1.0; the new state lives outside `board.json`.

1.0 added board schema 1.0 (stages, packages, runtime resources, budgets, contracts), runtime slots, exclusive gates, cross-harness claims, worktrees, profile L and the release and smoke checks.

## What it does

| Part | What it does |
|---|---|
| Planning | Interview, architecture, task plan, project files, briefs for the next 3–5 tasks |
| Write guard | While a task is in progress, agents may only write the files listed for it; a dependency manifest needs an approval, protected paths are lead-only, denied commands never pass |
| Stop check | Before an agent finishes, all changed files are compared with the task; foreign changes of other live claims are reported separately |
| Claims | One live session per task across harnesses, listed by `claim.py list` and `pl_status` |
| Worktrees | A task checkout with its own branch, runtime slot and claim (`worktree.py start`) |
| Runtime slots | Ports, test database and bucket per worktree, read from `.polier-slot` |
| Exclusive gates | Shared resources (e2e, load, DB reset) are locked; a busy one exits 75 and does not run |
| Gate records | `pl_gate` runs a test and saves the output; only that counts as proof |
| Checkpoints | `tools/state.py` moves a task through `in_progress → verifying → review → done`, with rework, block and fail paths |
| Policy | `policy.json`: limits, approvals, protected paths, denied and lead-only commands |
| Run records | `runs/<ID>.json`: attempts and events, committed with the task |
| Approvals | `reviews/approvals/AP-NNN.json`: request, grant, deny; read by the tools and the guard |
| Dispatch | `tools/dispatch.py`: waves, blocked tasks, scope conflicts, pending approvals |
| Audit | `tools/audit.py`: compliance view for every task, errors for `done` tasks with an enabled policy |
| Tools | `pl_status`, `pl_gate`, `pl_scope_check`, `pl_check`, `pl_next`, `pl_state` |

## Commands

In DeepSeek Harness (Claude Code uses `POLIER_ROLE` and `POLIER_TASK` instead, see its adapter README):

| Command | Effect |
|---|---|
| `/pl lead` | this session may write everything (planning, board, merge) |
| `/pl worker` | back to the current task's files (default) |
| `/pl reviewer` | this session writes only under `reviews/` |
| `/pl task M03` | bind this session to one task and claim it; `/pl task` releases the claim |
| `/pl status` | show role, task and allowed files |
| `/pl render` | regenerate `STATUS.md` (lead only) |
| `/pl next` | show the dispatch plan: next wave, blocked tasks, conflicts, pending approvals |
| `/pl policy` | show the active policy: limits, approval actions, protected paths, denied commands |

## Command-line tools

| Tool | Purpose |
|---|---|
| `tools/check.py` | lint a generated project (files, board, briefs, budgets, stages, packages, evidence, policy, runs, approvals, drift) |
| `tools/gate.py` | run one gate, lock `--exclusive` resources, write a checksummed record |
| `tools/render_status.py` | regenerate `STATUS.md` from `board.json` |
| `tools/scope_check.py` | changed files against the task's scope, with foreign-change detection |
| `tools/state.py` | `show`, `set`, `check` a task's state; the only writer of the board status in 1.1 |
| `tools/approve.py` | `request`, `grant`, `deny`, `list`, `check` approval records |
| `tools/dispatch.py` | the dispatch plan: waves, blocked tasks, conflicts, pending approvals |
| `tools/audit.py` | compliance view of the tasks against policy, runs, gates and reviews |
| `tools/slot.py` | `acquire`, `release`, `show`, `list` runtime slots per worktree |
| `tools/claim.py` | `take`, `release`, `beat`, `list` cross-harness task claims |
| `tools/worktree.py` | `start`, `finish` a task worktree with branch, slot and claim |
| `tools/boundaries.py` | cross-package import check (profile L) |
| `tools/contracts.py` | contract schemas, fixtures, versions and dependants (profile L) |
| `tools/release_check.py` | clean, tagged, merged release state (gate `release-clean`) |
| `tools/smoke.py` | post-deploy smoke check, recorded as a gate |
| `tools/drift.py` | project-local generator copy vs `tools/manifest.json` |
| `tools/manifest.py` | build or verify `tools/manifest.json` at release |

## Project files

```
my-project/
├── ARCHITECTURE.md   rules every module follows, one page
├── AGENTS.md         commands and rules for agents
├── board.json        tasks, dependencies, allowed files, status; stages/packages/resources at 1.0
├── policy.json       limits, approvals, protected paths, denied commands (1.1)
├── STATUS.md         progress, generated from board.json, runs/ and policy.json
├── tasks/            briefs for the next tasks
├── runs/             one execution record per task: attempts, events (1.1)
├── reviews/          reviews and gate records; approvals/AP-NNN.json (1.1)
├── docs/             module or package map, orchestration, quality gates, release and environment docs
└── packages/ services/ apps/   profile L only
```

## What the guard does not cover

The guard keeps honest agents on track; it is not a sandbox. Known gaps:

- **Approvals are cooperative evidence, not authentication.** `reviews/approvals/AP-NNN.json` has no signature and no identity check. Whoever can write the file can forge a granted record, and a shell write is outside the guard. Commit the approval and review it like code.
- **Run records can be forged.** `runs/<ID>.json` is a text file that a hand edit or a shell write can change as easily as the tools; `tools/audit.py` compares it with the board and the evidence folder, not with what happened. A `done` task whose run record was edited is only visible as a contradiction.
- **Command matching is static.** The policy's denied and lead-only patterns are matched against shell segments after quotes, heredocs, assignments and wrappers are stripped, so `git push` is caught. A command assembled by a variable, `eval`, an interpreter or a script file is not.
- **The policy is a file.** Whoever can write `policy.json` can widen the rules. Protect it like the board and review changes to it; the guard reads it, it does not own it.
- **Shell writes it cannot see.** DeepSeek Harness checks only its file tools before a write. Claude Code also checks `Bash`, but only what a static look at the command shows (redirections, `tee`, `cp`/`mv`, `rm`, `touch`, `sed -i`, `perl -i`, `dd of=`, `bash -c`). Not seen: interpreters and scripts (`python -c`, `node -e`, `./build.sh`), build tools and package managers, git commands (`checkout`, `restore`, `stash`, `apply`, `commit`), `xargs`, `find -exec`/`-delete`, `patch`, and paths with variables, globs or `$(...)`. These writes reach only the stop check.
- **The stop check sees only `git status`.** Committed changes, ignored files (`.gitignore`, `.git/info/exclude`) and files outside the repository are invisible. It gives up after `maxStopReminders` (DSH) / `POLIER_MAX_STOP_REMINDERS` (Claude Code) reminders, and it does not run with several tasks in progress, for lead or reviewer sessions, without git, or when it fails.
- **The board is read on every call.** A shell write the guard cannot see can change `board.json` (task status, `scope_write`) and so widen or switch off the guard. The stop check reports the board change, but only while one task is still `in_progress`; `tools/audit.py` shows a status that the run record does not support.
- **Paths are compared as text.** Symlinks are not followed, so a link inside the scope can point outside it. The comparison ignores case on macOS and Windows, where the file system does, but two different spellings on a case-sensitive file system are two different paths. Protected-path patterns use the same comparison.
- **The project is found from the session folder.** A session that starts outside the project, or in a worktree whose `board.json` still shows the task as `pending`, is not guarded until it is bound to a task (`/pl task` in DSH, `POLIER_TASK` in Claude Code).
- **Claims are cooperative.** A live claim stops a second session that uses the claim tools and names the holder; a session that never claims is not stopped by a claim alone. A claim is not a lock on files.
- **Gate records can be forged.** `reviews/evidence/` is always writable, and an agent can write a log and a matching record itself; the gate command is free text. A reviewer must compare the recorded command with `AGENTS.md`.
- **It fails open.** If Python is missing or a hook fails, the write goes through. Roles live in memory (DSH) or in environment variables (Claude Code); whoever can edit the settings can lift them.
- **The kill warning is advisory.** `kill`, `pkill` and `killall` never block a command: DSH sends a message, Claude Code asks. A sandbox is the only real protection against stopping another session's processes.
- **Claude Code specifics.** Only `Write`, `Edit`, `MultiEdit`, `NotebookEdit` and `Bash` are checked, not MCP or other tools that write files. Bash writes outside the project to `/tmp`, the temp folder or `/dev` are not checked, and deleting a file git does not track is allowed (it undoes a write).

For hard limits, run workers in a sandbox or a container with write access to the task's files only.

## Package layout

The rules are separate from the harness, so they can run in other hosts too.

| Folder | What it holds |
|---|---|
| `core/` | Board reading (schema 0.9 and 1.0), write guard, stop check, gate records, claims, slots, locks, boundaries, and the 1.1 modules: `policy.py`, `runs.py`, `approvals.py`, `state.py`, `dispatch.py`, `audit.py`. Python 3.9+, standard library only, no harness code. Tests in `core/tests/`. |
| `adapters/dsh/` | The DeepSeek Harness plugin. It maps harness events and tool names onto `core/`, including the policy guard in `lib/policy.mjs` (see [`adapters/README.md`](adapters/README.md)). |
| `adapters/claude-code/` | Claude Code hooks (`PreToolUse`, `Stop`) that call `core/`, policy checks included. |
| `tools/` | Command-line tools built on `core/`; the table above lists them. |
| `templates/` | Canonical artifacts: board schema, policy, AGENTS, briefs, orchestration, contracts, release, environments, gates, design rules. |
| `prompt/` | The process (`generator.md`), the shipped orchestration model (`orchestration.md`), the rubric and the DeepSeek Harness mapping. |
| `examples/` | Reference projects: `minimal-cli` (profile S, the 0.9 compatibility reference) and `monorepo-mini` (profile L, the 1.1 reference); the CI validates both with `check.py`. |

An adapter for git hooks is planned. Run all tests with `npm test`; the core alone with `python3 -m unittest discover -s core/tests -t .`.

## More

- Step-by-step checklist: [`guide/cheatsheet.md`](guide/cheatsheet.md)
- Full process: [`prompt/generator.md`](prompt/generator.md)
- Orchestration model: [`prompt/orchestration.md`](prompt/orchestration.md)
- Quality rubric: [`prompt/rubric.md`](prompt/rubric.md)
- DeepSeek Harness details and plugin settings: [`prompt/dsh.md`](prompt/dsh.md)
- Example projects: [`examples/minimal-cli`](examples/minimal-cli/) (profile S, the 0.9 compatibility reference) and [`examples/monorepo-mini`](examples/monorepo-mini/) (profile L, the 1.1 reference)
- Changes and updates: [`CHANGELOG.md`](CHANGELOG.md)
- Skill only, without the plugin: `./install.sh`

## License

[MIT](LICENSE)
