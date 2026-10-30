# Quickstart

Start the dashboard for a project and take one task from `pending` to `done`. It takes about ten minutes with the bundled example project.

## Requirements

- Python 3.9 or newer, git
- A Polier project (a folder with `board.json`), or an empty folder to plan a new one
- Optional: the Claude Code CLI for headless agent sessions

## 1. Start the dashboard

```bash
git clone https://github.com/atshv/Polier && cd Polier
python3 tools/serve.py examples/monorepo-mini --port 8765 --open
```

The server binds to `127.0.0.1` and serves one page. Stop it with Ctrl+C. Without `board.json` the page opens the **Plan editor** with the interview instead; on a fresh machine the guided setup opens first.

> [!TIP]
> On a machine where the dashboard has not run before, the guided [first-run setup](polier:setup) opens first: connect GitHub, pick the AI provider, sign in and choose a model. **Skip setup** goes on to the board (or the plan editor without `board.json`).

## 2. Find your way

- The **sidebar** groups the views: your work, planning, tracking, agents and knowledge.
- **Ctrl/Cmd+K** opens the command palette: every view, every task and the quick actions.
- **/** focuses the task search, **?** lists the shortcuts.

## 3. Open a task

Open **Board** and click a card in **Pending**. The drawer shows the brief, the gates, the run record, the review and the worklog. The **Status** row only offers transitions the state machine allows.

## 4. Move it through the checkpoints

1. **Claim task** — one live session per task.
2. **→ In progress** — refused while a dependency is open.
3. Run every gate from the **Gates** tab; each run writes a record with exit code and log hash.
4. **→ Verifying**, then **→ Reviewing** — refused until every gate has a passing record.
5. A reviewer writes `reviews/<ID>.md` with `verdict: pass`, then **→ Done**.

> [!TIP]
> Every refusal says which command produces the missing proof. The same rules apply in the CLI: `python3 tools/state.py set ENG-01 in_progress`.

## 5. Check your queue

**Your Work** collects what needs you: the inbox (approvals, failed gates, blocked tasks, budget warnings), review requests and ready tasks.

## Next steps

- [Plan a new project](polier:plan-a-project)
- [Run agents headless](polier:agent-sessions)
- [Organise work with labels and views](polier:organise-work)
