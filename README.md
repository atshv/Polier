# Polier

Plan an AI coding project before the first line of code, then keep the agents to the plan.

![version](https://img.shields.io/badge/version-0.8.0-blue?style=flat-square)
![license](https://img.shields.io/badge/license-MIT-green?style=flat-square)

*Polier* is the German word for the site foreman, the one who keeps the crew to the plan. Polier is a DeepSeek Harness plugin and agent skill. It interviews you, drafts a one-page architecture and a task plan, and after your approval writes a project scaffold that coding agents build from, one reviewed task at a time. As a plugin it also enforces the plan while agents build: writes outside a task's scope are blocked, and gate results are recorded so they cannot be made up.

## Quick start

Requirements: DeepSeek Harness, git, Python 3.9+.

```bash
git clone https://github.com/atshv/polier.git
dsh plugin --profile web add ./polier
```

Use your own profile name instead of `web`, then restart the harness. Without the plugin, install only the skill with `./install.sh` (see [Installation and updates](#installation-and-updates)).

Open a new DSH session in an empty project folder and write:

> Plan a new project: a command-line tool that stores my bookmarks locally and finds them again.

The generator asks its questions, shows the plan for approval, writes the scaffold and hands over the prompt for the first task.

## How it works

```mermaid
flowchart LR
    A[Interview] --> B[Architecture + task plan] --> C{Approve}
    C -- revise --> B
    C -- yes --> D[Scaffold + 3–5 task briefs] --> E[Agent builds a task] --> F[Independent review]
    F -- next task --> E
    F -- stage done --> D
```

| Step | Result |
|---|---|
| Interview | goals, definition of done, constraints, team size |
| Plan | one-page architecture, task DAG with scopes and gates |
| Scaffold | git repository, rules for agents, briefs for the next 3–5 tasks |
| Build | one task per session, verified by deterministic gates |
| Review | a separate agent checks every acceptance criterion against the diff |

## What you get

```
my-project/
├── ARCHITECTURE.md   invariants, one page
├── AGENTS.md         commands and rules every agent follows
├── board.json        tasks, dependencies, write scopes, status
├── STATUS.md         progress and next tasks, generated from board.json
├── tasks/            briefs for the next 3–5 tasks
├── reviews/          review results per task
└── docs/             module map, quality gates, decisions
```

## Principles

- **One-page architecture** — only the invariants that keep modules consistent.
- **Just in time** — only the next 3–5 tasks are specified in detail.
- **Gates before opinions** — deterministic checks run before any review.
- **Independent review** — no agent approves its own work.
- **Right-sized team** — one writer by default; parallel agents only for parallel work.
- **Traceable** — definition of done → task → acceptance criterion → gate, enforced by `tools/check.py`.

## In DeepSeek Harness

The plugin registers the skill and adds four parts around the build.

| Part | What it does |
|---|---|
| Write guard | While a task is `in_progress`, `write`, `edit` and `str_replace_editor` work only inside its `scope_write`, never in `scope_write_forbidden`. `board.json`, `STATUS.md` and `tasks/` are lead-owned; `reviews/evidence/` is always open. |
| Stop check | Before a turn ends, the git diff is compared with the scope. Changes made through `bash` are caught here and sent back to the agent. |
| Tools | `pl_status` (running and ready tasks, scope, handoffs), `pl_gate` (runs a gate, writes a record), `pl_scope_check`, `pl_check`. |
| `/pl` | Your command per session: `/pl lead` before planning, merging or editing the board, `/pl worker` to return, `/pl reviewer` for review sessions (writes only under `reviews/`), `/pl task M03` with several tasks in progress, `/pl status`, `/pl render`. |

Every session starts as a worker, also after a restart. Configure the plugin row in the profile with `enforce: deny | ask | off`, `stopCheck`, `maxStopReminders`, `python` and `skill` (defaults in [`cordis.patch.yml`](cordis.patch.yml)). Gate commands run through the harness shell and its sandbox on macOS and Linux; on Windows they run as a direct process.

## Installation and updates

| Task | Command |
|---|---|
| Plugin (skill + guard + tools) | `dsh plugin --profile <name> add ./polier` |
| Update the plugin | `git -C polier pull && dsh plugin --profile <name> add ./polier` |
| Remove the plugin | `dsh plugin --profile <name> remove dsh-polier` |
| Skill only, all projects | `./install.sh --ref "v$(cat VERSION)"` |
| Install for one project | `./install.sh <project>/.dsh/skills` |
| Update to the latest version | `git pull && ./update.sh --ref "v$(cat VERSION)"` |
| Roll back | `./update.sh --ref v0.5.6` |
| Claude Code | add the target `claude` to any command above |

Use either the plugin or `install.sh`, not both, or the skill exists twice. Without `--ref`, the scripts install the current checkout, including uncommitted changes. Before updating a running project, read [`CHANGELOG.md`](CHANGELOG.md); update between stages, never during a task.

Without skill support, attach `prompt/generator.md`, `prompt/rubric.md`, `templates/` and `tools/` to the chat and fill in the input block at the top of `prompt/generator.md`.

## Repository

```
├── SKILL.md            skill entry point
├── dsh/                DeepSeek Harness plugin (index.mjs, lib/, test/); package.json, cordis.patch.yml
├── prompt/             generator.md (process), rubric.md (quality), dsh.md (DSH tool mapping)
├── templates/          artifact templates and board schema
├── tools/              check.py (validation), render_status.py (STATUS.md),
│                       gate.py (gate run + record), scope_check.py (diff vs. scope)
├── tests/              unittest for the tools; `npm test` runs these and the plugin tests
├── guide/              cheatsheet.md: checklists for the human
├── examples/           minimal-cli: reference project
├── install.sh          install, update.sh: update or roll back
└── CHANGELOG.md        releases and migration steps; current version in VERSION
```

## Example

[`examples/minimal-cli`](examples/minimal-cli/) is a bookmark CLI with six tasks, captured during the third task: the [generator input](examples/minimal-cli/project-input.md), the [architecture](examples/minimal-cli/ARCHITECTURE.md), the [current brief](examples/minimal-cli/tasks/M03.md) and its [first review](examples/minimal-cli/reviews/M03.md).

```bash
python3 tools/check.py examples/minimal-cli
```

M01 and M02 were finished before 0.7.0 and still carry free-text evidence, so `check.py` passes with two warnings. Tasks done from now on use the record paths from `pl_gate` or `tools/gate.py`.

## License

[MIT](LICENSE). Ideas from BMAD-METHOD, GitHub Spec Kit, Claude Code agent teams, Cognition, Anthropic's evaluator-optimizer pattern and AGENTS.md.
