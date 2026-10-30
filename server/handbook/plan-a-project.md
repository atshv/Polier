# Plan a new project

Turn an idea into an approved plan: architecture, stages, tasks and policy. You answer questions; a generator session writes the files; you approve.

## Before you start

- An empty folder with `git init`, or an existing repository (brownfield)
- The dashboard running for that folder: `python3 tools/serve.py /path/to/project`
- A session provider for the generator (Claude Code by default, see [Agent sessions](polier:agent-sessions))

## 1. Answer the interview

Without `board.json` the dashboard opens the **Plan editor** with the interview (on a fresh machine the guided [first-run setup](polier:setup) opens first; **Skip setup** leads here). The questions cover mode (greenfield or brownfield), name, goal, non-goals, platform, stack, data, hosting, release path and hard constraints.

- **Save answers** keeps a draft in the local runtime folder; nothing is committed yet.
- Leave a question empty when you do not know the answer. It becomes an `open_questions` entry on the board instead of a guess.

## 2. Generate the plan

**Generate plan** composes the generator prompt with your answers and starts a headless generator session. Watch it in **Sessions**. It writes:

| File | Contents |
|---|---|
| `ARCHITECTURE.md` | one page of rules every module follows |
| `board.json` | stages, tasks, dependencies, scopes, gates |
| `tasks/<ID>.md` | briefs for the first three to five tasks |
| `policy.json` | limits, approvals, protected paths, denied commands |
| `AGENTS.md` | commands and rules for agents |

## 3. Review and approve

Read `ARCHITECTURE.md` and the board in **Pages** and **Dependencies**. Then **Approve plan**: the board is validated (schema, dependency cycles, scopes) and your approval is recorded.

> [!WARNING]
> Approve only what you would defend in a review. Changing a stage later is possible, but every task brief builds on the architecture page.

## 4. Adjust the plan

The Plan editor edits tasks, dependencies, scopes, gates and stage decisions with the same validation as the CLI:

```bash
python3 tools/plan.py create --title "Export bookmarks" --goal "CSV export" \
  --stage surface --scope-write src/export/ --acceptance A1 --gates unit
python3 tools/plan.py update EXP-01 --depends-on CORE-02 --estimate-hours 3
```

Only `pending`, `blocked` and `failed` tasks can be deleted; done tasks are reopened through the state machine first.

## Next

[Run a task](polier:run-a-task) — take the first task of the plan to `done`.
