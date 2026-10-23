# Polier

Plan an AI coding project before the first line of code, then keep the agents to the plan.

![version](https://img.shields.io/badge/version-0.8.0-blue?style=flat-square)
![license](https://img.shields.io/badge/license-MIT-green?style=flat-square)

A plugin for [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness). It interviews you, writes a one-page architecture and a task plan, and after your approval sets up the project. While agents build, it blocks writes outside the current task and records test results as proof.

## Install

Requirements: DeepSeek Harness, git, Python 3.9+.

```bash
git clone https://github.com/atshv/polier.git
dsh plugin --profile web add ./polier
```

Use your own profile name instead of `web`, then restart the harness.

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

## More

- Step-by-step checklist: [`guide/cheatsheet.md`](guide/cheatsheet.md)
- Full process: [`prompt/generator.md`](prompt/generator.md)
- DeepSeek Harness details and plugin settings: [`prompt/dsh.md`](prompt/dsh.md)
- Example project: [`examples/minimal-cli`](examples/minimal-cli/)
- Changes and updates: [`CHANGELOG.md`](CHANGELOG.md)
- Skill only, without the plugin: `./install.sh`

## License

[MIT](LICENSE)
