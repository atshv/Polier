# Command-line tools

Every dashboard action has a CLI equivalent. All tools take `--root <project>` (default: the current folder) and use only the Python standard library.

## Daily work

| Tool | Purpose |
|---|---|
| `tools/state.py show\|check\|set` | read or change a task's status — the only writer of the status |
| `tools/gate.py` | run one gate and write a checksummed record |
| `tools/claim.py take\|release\|list` | one live session per task |
| `tools/dispatch.py` | the next wave, blocked tasks, conflicts, pending approvals |
| `tools/approve.py request\|grant\|deny\|list` | owner decisions |
| `tools/session.py run\|list\|show\|stop` | headless agent sessions |

## Planning and organising

| Tool | Purpose |
|---|---|
| `tools/plan.py create\|update\|delete\|stage` | edit tasks, labels, estimates, dates and stage decisions |
| `tools/settings.py show\|init\|feature\|me\|label` | `dashboard.json`: features, labels, your handle |
| `tools/views.py list\|save\|delete` | saved views |
| `tools/intake.py add\|accept\|reject` | intake proposals |
| `tools/templates.py list\|save\|delete` | task templates |
| `tools/automations.py validate\|run` | automation rules and the dry run |

## Checks and reports

| Tool | Purpose |
|---|---|
| `tools/check.py` | lint the whole project: files, board, briefs, policy, evidence |
| `tools/audit.py` | every task against policy, runs, gates and reviews |
| `tools/render_status.py [--html] [--watch]` | `STATUS.md` and the static `STATUS.html` |
| `tools/usage.py` | tokens per task against the budget |
| `tools/pages.py`, `tools/github.py`, `tools/assistant.py` | knowledge, PRs and CI, the assistant |
| `tools/serve.py` | the dashboard |

Exit codes are the same everywhere: `0` ok, `1` refused or failed, `2` usage or environment error.
