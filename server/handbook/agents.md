# Agents

An agent is a reusable profile you assign to work: a role, an optional model, standing instructions, the skills it follows and the MCP connectors it may use. Assigning an agent to a task starts a headless session with that setup.

## The built-in agents

Without an `agents.json`, three profiles are ready to use:

| Agent | Role | Skills |
|---|---|---|
| **Builder** | `worker` — implements a task in a worktree | Stay in scope, Write tests first, Prove it with gates, Write a handoff |
| **Reviewer** | `reviewer` — writes `reviews/<ID>.md` with a verdict | Review checklist |
| **Lead** | `lead` — runs gates and moves the status | Prove it with gates |

Their skills come from the examples shipped with Polier, so they work before you add any skill to the project.

## Create or edit an agent

**AI → Agents → New agent** (or **Edit** on a card):

| Field | Meaning |
|---|---|
| Name, ID | how it shows up; the ID is used in the API and `agents.json` |
| Role | `worker`, `reviewer` or `lead` — decides what the write guard allows |
| Model | optional; otherwise the model from **Settings → Sessions** |
| Description | one line, shown on the card and in the prompt |
| Instructions | standing guidance, e.g. "UI work follows docs/design-rules.md" |
| Skills | which [skills](polier:skills) are inlined into the prompt |
| MCP connectors | which [connectors](polier:mcp-connectors) it gets; none ticked = all enabled for the role |
| Worktree | run in a task worktree by default |

Saving writes `agents.json` to the project root. Commit it so the team shares the same agents. Connectors are referenced by name; each machine configures its own.

## Assign an agent

- **Agents → Assign to a task…** — pick the task, add a note, start.
- **Task drawer → Session** — choose the agent in the first select.
- **Sessions → Start a session** — choose task and agent.

```bash
curl -s -X POST http://127.0.0.1:8765/api/sessions \
  -H "X-Polier-Action: 1" -H "Content-Type: application/json" \
  -d '{"agent": "builder", "task": "ENG-01"}'
```

The session claims the task, runs under the write guard with the agent's role, and records its tokens in `runs/<ID>.json`. Watch it in **Sessions**.

## What the agent receives

The prompt is the normal task prompt (goal, scope, gates, acceptance, where the brief is) plus:

```markdown
## Agent: Builder

Implements a task inside its scope and proves it with the gates.

<instructions>

## Skills

Follow these skills whenever their description applies to what you are doing.

### Write tests first

_When: Use when implementing behaviour that acceptance criteria describe…_

1. Read the acceptance criteria …
```

With Claude Code, the connectors arrive as an `--mcp-config` file and `mcp__<name>` entries in the allowed tools.
