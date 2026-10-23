# Polier

Plan an AI coding project before the first line of code, then keep the agents to the plan.

![version](https://img.shields.io/badge/version-0.9.0-blue?style=flat-square)
![license](https://img.shields.io/badge/license-MIT-green?style=flat-square)

A plugin for [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness), with hooks for Claude Code. It interviews you, writes a one-page architecture and a task plan, and after your approval sets up the project. While agents build, it blocks writes outside the current task and records test results as proof.

## Install

Requirements: DeepSeek Harness, git, Python 3.9+.

```bash
git clone https://github.com/atshv/polier.git
dsh plugin --profile web add ./polier
```

Use your own profile name instead of `web`, then restart the harness.

**Claude Code:** run `./install.sh claude`, then add the hooks from [`adapters/claude-code/settings.example.json`](adapters/claude-code/settings.example.json) to `.claude/settings.json`. Details, roles and settings: [`adapters/claude-code/README.md`](adapters/claude-code/README.md).

## Start

Open a new session in an empty folder and write:

> Plan a new project: a command-line tool that stores my bookmarks locally and finds them again.

Polier asks its questions, shows the plan for approval, writes the project files and gives you the prompt for the first task.

## What it does

| Part | What it does |
|---|---|
| Planning | Interview, architecture, task plan, project files, briefs for the next 3–5 tasks |
| Write guard | While a task is in progress, agents may only write the files listed for it |
| Stop check | Before an agent finishes, all changed files are compared with the task |
| Gate records | `pl_gate` runs a test and saves the output; only that counts as proof |
| Tools | `pl_status`, `pl_gate`, `pl_scope_check`, `pl_check` |

## Commands

In DeepSeek Harness (Claude Code uses `POLIER_ROLE` and `POLIER_TASK` instead, see its adapter README):

| Command | Effect |
|---|---|
| `/pl lead` | this session may write everything (planning, board, merge) |
| `/pl worker` | back to the current task's files (default) |
| `/pl reviewer` | this session writes only under `reviews/` |
| `/pl task M03` | bind this session to one task |
| `/pl status` | show role, task and allowed files |
| `/pl render` | regenerate `STATUS.md` (lead only) |

## Project files

```
my-project/
├── ARCHITECTURE.md   rules every module follows, one page
├── AGENTS.md         commands and rules for agents
├── board.json        tasks, dependencies, allowed files, status
├── STATUS.md         progress, generated from board.json
├── tasks/            briefs for the next tasks
├── reviews/          reviews and gate records
└── docs/             module map, quality gates, decisions
```

## What the guard does not cover

The guard keeps honest agents on track; it is not a sandbox. Known gaps:

- **Shell writes it cannot see.** DeepSeek Harness checks only its file tools before a write. Claude Code also checks `Bash`, but only what a static look at the command shows (redirections, `tee`, `cp`/`mv`, `rm`, `touch`, `sed -i`, `perl -i`, `dd of=`, `bash -c`). Not seen: interpreters and scripts (`python -c`, `node -e`, `./build.sh`), build tools and package managers, git commands (`checkout`, `restore`, `stash`, `apply`, `commit`), `xargs`, `find -exec`/`-delete`, `patch`, and paths with variables, globs or `$(...)`. These writes reach only the stop check.
- **The stop check sees only `git status`.** Committed changes, ignored files (`.gitignore`, `.git/info/exclude`) and files outside the repository are invisible. It gives up after `maxStopReminders` (DSH) / `POLIER_MAX_STOP_REMINDERS` (Claude Code) reminders, and it does not run with several tasks in progress, for lead or reviewer sessions, without git, or when it fails.
- **The board is read on every call.** A shell write the guard cannot see can change `board.json` (task status, `scope_write`) and so widen or switch off the guard. The stop check reports the board change, but only while one task is still `in_progress`.
- **Paths are compared as text.** Symlinks are not followed, so a link inside the scope can point outside it. On case-insensitive file systems (macOS, Windows) `Board.json` or `SRC/app.py` slip past the rules.
- **The project is found from the session folder.** A session that starts outside the project, or in a worktree whose `board.json` still shows the task as `pending`, is not guarded until it is bound to a task.
- **Gate records can be forged.** `reviews/evidence/` is always writable, and an agent can write a log and a matching record itself; the gate command is free text. A reviewer must compare the recorded command with `AGENTS.md`.
- **It fails open.** If Python is missing or a hook fails, the write goes through. Roles live in memory (DSH) or in environment variables (Claude Code); whoever can edit the settings can lift them.
- **Claude Code specifics.** Only `Write`, `Edit`, `MultiEdit`, `NotebookEdit` and `Bash` are checked, not MCP or other tools that write files. Bash writes outside the project to `/tmp`, the temp folder or `/dev` are not checked, and deleting a file git does not track is allowed (it undoes a write).

For hard limits, run workers in a sandbox or a container with write access to the task's files only.

## Package layout

The rules are separate from the harness, so they can run in other hosts too.

| Folder | What it holds |
|---|---|
| `core/` | Write guard, stop check, gate records, board reading. Python 3.9+, standard library only, no harness code. Tests in `core/tests/`. |
| `adapters/dsh/` | The DeepSeek Harness plugin. It maps harness events and tool names onto `core/` (see [`adapters/README.md`](adapters/README.md)). |
| `adapters/claude-code/` | Claude Code hooks (`PreToolUse`, `Stop`) that call `core/`. |
| `tools/` | Command-line tools (`gate.py`, `scope_check.py`, `check.py`, `render_status.py`) built on `core/`. |

An adapter for git hooks is planned. Run all tests with `npm test`; the core alone with `python3 -m unittest discover -s core/tests -t .`.

## More

- Step-by-step checklist: [`guide/cheatsheet.md`](guide/cheatsheet.md)
- Full process: [`prompt/generator.md`](prompt/generator.md)
- DeepSeek Harness details and plugin settings: [`prompt/dsh.md`](prompt/dsh.md)
- Example project: [`examples/minimal-cli`](examples/minimal-cli/)
- Changes and updates: [`CHANGELOG.md`](CHANGELOG.md)
- Skill only, without the plugin: `./install.sh`

## License

[MIT](LICENSE)
