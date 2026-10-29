# Connect Claude Code

Give your interactive Claude Code session the board as tools, without starting the dashboard.

## Add the MCP server

```bash
claude mcp add polier -- python3 /path/to/Polier/tools/mcp.py --root /path/to/project
```

Restart the session. Ask "what is ready to start?" and Claude calls `polier_dispatch`.

## Tools

| Tool | Kind | Purpose |
|---|---|---|
| `polier_snapshot`, `polier_tasks`, `polier_task`, `polier_show` | read | the board, one task |
| `polier_dispatch`, `polier_activity`, `polier_approvals`, `polier_claims` | read | plan, feed, decisions, claims |
| `polier_me`, `polier_inbox`, `polier_worklog`, `polier_settings`, `polier_views` | read | your queue, effort, settings and views |
| `polier_timeline`, `polier_cycles`, `polier_modules`, `polier_coverage`, `polier_analytics` | read | planning views |
| `polier_pages`, `polier_page`, `polier_pages_search`, `polier_intake`, `polier_templates` | read | knowledge and templates |
| `polier_automations`, `polier_github` | read | automation dry run, PRs and CI |
| `polier_state_set`, `polier_gate`, `polier_claim`, `polier_release` | write | lead actions |
| `polier_intake_add`, `polier_inbox_read` | write | intake, read marks |

Write tools are refused with `--read-only`.

## Hooks

To guard an interactive session as well, add the hooks from `adapters/claude-code/settings.example.json` to `.claude/settings.json` and set `POLIER_ROLE` and `POLIER_TASK` for the session.
