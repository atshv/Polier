# Polier

Plan an AI coding project before the first line of code, then keep the agents to the plan.

[![release](https://img.shields.io/github/v/release/atshv/Polier?style=flat-square)](https://github.com/atshv/Polier/releases)
![license](https://img.shields.io/badge/license-MIT-green?style=flat-square)

A plugin for [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness), with hooks for Claude Code. Polier (German for site foreman) interviews you, writes a one-page architecture and a task plan, and sets up the project after your approval. While agents build, it blocks writes outside the current task, accepts only recorded test runs as proof, and commits a record of every attempt, approval and review round.

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

## What's new

**1.1** adds orchestration on top of the plan: `policy.json` (limits, protected paths, approvals, denied commands), checkpoints through `tools/state.py`, run records in `runs/`, approvals in `reviews/approvals/`, plus `dispatch.py` and `audit.py`. Projects without `policy.json` keep the 1.0 behaviour.

**1.0** added board schema 1.0, runtime slots, exclusive gates, claims across harnesses, worktrees, profile L and release and smoke checks.

Details and migration steps for every version: [`CHANGELOG.md`](CHANGELOG.md) and [Releases](https://github.com/atshv/Polier/releases).

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
| `/pl off` | switch the guard off for this session |
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

## Releasing

Releases are automatic. To publish a new version:

1. Set the new number in `VERSION` (for example `1.2.0`).
2. Add a section `## 1.2.0` at the top of `CHANGELOG.md` with what changed and how to migrate.
3. Push or upload both to `main`.

The workflow [`.github/workflows/release.yml`](.github/workflows/release.yml) then syncs `package.json` and `tools/manifest.json`, creates the tag `v1.2.0` and publishes a GitHub Release with the changelog section as its notes. It stops with a clear message when the changelog section is missing. A release that already exists is never overwritten.

## License

[MIT](LICENSE)
