# Polier

Plan an AI coding project before the first line of code, then keep the agents to the plan.

![version](https://img.shields.io/badge/version-1.0.0-blue?style=flat-square)
![license](https://img.shields.io/badge/license-MIT-green?style=flat-square)

A plugin for [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness), with hooks for Claude Code. It interviews you, writes a one-page architecture and a task plan, and after your approval sets up the project. While agents build, it blocks writes outside the current task and records test results as proof.

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

Polier asks its questions, shows the plan for approval, writes the project files and gives you the prompt for the first task.

## What's new in 1.0

1.0 is for projects with several agents and several deployable parts — the gaps a real parallel run exposed:

- **Board schema 1.0** — opt-in with `"schema_version": "1.0"`: stages with exit criteria and owner decisions, packages, runtime resources, budgets, worktrees and machine-readable contracts. 0.9 boards stay valid.
- **Runtime slots** — one port set, test database and bucket per worktree, in `.polier-slot`, so two checkouts can run servers and tests at once.
- **Exclusive gates and infrastructure classification** — e2e, load and DB gates lock a shared resource; a busy resource or a connection failure is recorded as `busy`/`infra`, never mistaken for a broken test.
- **Cross-harness claims** — a task has one live session, visible from DeepSeek Harness and Claude Code; a heartbeat expires claims of crashed sessions.
- **Worktrees and foreign changes** — M/L work happens in the task's worktree; changes made by another live session are reported as foreign, not blamed on the current task.
- **Monorepo profile L** — packages, services and apps with their own short architecture files, an enforced package map (`boundaries`), versioned contracts and a release environment checklist.
- **Release and smoke gates** — `release_check.py` (clean tree, tagged HEAD on the base branch, released stages done) and `smoke.py` (post-deploy checks, values from the environment).
- **UI briefs with numbers** — target values in px/ms/tokens, all states, screenshot evidence; a UI task without numbers is not ready.
- **Drift detection** — the project-local Polier copy is compared with `tools/manifest.json`; `check.py` names files that were edited locally or are outdated.
- **Guard extras** — `kill`/`pkill`/`killall` commands are flagged (a warning, never a denial) and paths compare case-insensitively on macOS/Windows.
- **Reference projects** — `examples/minimal-cli` for profile S and `examples/monorepo-mini` for profile L (packages, contracts, stages, runtime resources and release docs), both validated by CI.

## What it does

| Part | What it does |
|---|---|
| Planning | Interview, architecture, task plan, project files, briefs for the next 3–5 tasks |
| Write guard | While a task is in progress, agents may only write the files listed for it |
| Stop check | Before an agent finishes, all changed files are compared with the task; foreign changes of other live claims are reported separately |
| Claims | One live session per task across harnesses, listed by `claim.py list` and `pl_status` |
| Worktrees | A task checkout with its own branch, runtime slot and claim (`worktree.py start`) |
| Runtime slots | Ports, test database and bucket per worktree, read from `.polier-slot` |
| Exclusive gates | Shared resources (e2e, load, DB reset) are locked; a busy one exits 75 and does not run |
| Gate records | `pl_gate` runs a test and saves the output; only that counts as proof |
| Tools | `pl_status`, `pl_gate`, `pl_scope_check`, `pl_check` |

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

## Command-line tools

| Tool | Purpose |
|---|---|
| `tools/check.py` | lint a generated project (files, board, briefs, budgets, stages, packages, evidence, drift) |
| `tools/gate.py` | run one gate, lock `--exclusive` resources, write a checksummed record |
| `tools/render_status.py` | regenerate `STATUS.md` from `board.json` |
| `tools/scope_check.py` | changed files against the task's scope, with foreign-change detection |
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
├── STATUS.md         progress, generated from board.json
├── tasks/            briefs for the next tasks
├── reviews/          reviews and gate records
├── docs/             module or package map, quality gates, decisions, release and environment docs
└── packages/ services/ apps/   profile L only
```

## What the guard does not cover

The guard keeps honest agents on track; it is not a sandbox. Known gaps:

- **Shell writes it cannot see.** DeepSeek Harness checks only its file tools before a write. Claude Code also checks `Bash`, but only what a static look at the command shows (redirections, `tee`, `cp`/`mv`, `rm`, `touch`, `sed -i`, `perl -i`, `dd of=`, `bash -c`). Not seen: interpreters and scripts (`python -c`, `node -e`, `./build.sh`), build tools and package managers, git commands (`checkout`, `restore`, `stash`, `apply`, `commit`), `xargs`, `find -exec`/`-delete`, `patch`, and paths with variables, globs or `$(...)`. These writes reach only the stop check.
- **The stop check sees only `git status`.** Committed changes, ignored files (`.gitignore`, `.git/info/exclude`) and files outside the repository are invisible. It gives up after `maxStopReminders` (DSH) / `POLIER_MAX_STOP_REMINDERS` (Claude Code) reminders, and it does not run with several tasks in progress, for lead or reviewer sessions, without git, or when it fails.
- **The board is read on every call.** A shell write the guard cannot see can change `board.json` (task status, `scope_write`) and so widen or switch off the guard. The stop check reports the board change, but only while one task is still `in_progress`.
- **Paths are compared as text.** Symlinks are not followed, so a link inside the scope can point outside it. The comparison ignores case on macOS and Windows, where the file system does, but two different spellings on a case-sensitive file system are two different paths.
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
| `core/` | Board reading (schema 0.9 and 1.0), write guard, stop check, gate records, claims, slots, locks, boundaries. Python 3.9+, standard library only, no harness code. Tests in `core/tests/`. |
| `adapters/dsh/` | The DeepSeek Harness plugin. It maps harness events and tool names onto `core/` (see [`adapters/README.md`](adapters/README.md)). |
| `adapters/claude-code/` | Claude Code hooks (`PreToolUse`, `Stop`) that call `core/`. |
| `tools/` | Command-line tools built on `core/`; the table above lists them. |
| `templates/` | Canonical artifacts: board schema, architecture, AGENTS, briefs, contracts, release, environments, gates, design rules. |
| `prompt/` | The process (`generator.md`), the rubric and the DeepSeek Harness mapping. |
| `examples/` | Reference projects: `minimal-cli` (profile S) and `monorepo-mini` (profile L); the CI validates both with `check.py`. |

An adapter for git hooks is planned. Run all tests with `npm test`; the core alone with `python3 -m unittest discover -s core/tests -t .`.

## More

- Step-by-step checklist: [`guide/cheatsheet.md`](guide/cheatsheet.md)
- Full process: [`prompt/generator.md`](prompt/generator.md)
- Quality rubric: [`prompt/rubric.md`](prompt/rubric.md)
- DeepSeek Harness details and plugin settings: [`prompt/dsh.md`](prompt/dsh.md)
- Example projects: [`examples/minimal-cli`](examples/minimal-cli/) (profile S) and [`examples/monorepo-mini`](examples/monorepo-mini/) (profile L)
- Changes and updates: [`CHANGELOG.md`](CHANGELOG.md)
- Skill only, without the plugin: `./install.sh`

## License

[MIT](LICENSE)
