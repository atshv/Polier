# Assistant

Ask the project questions in plain language and get answers grounded in the board, the run records, approvals, claims, sessions and intake.

## Ask

Open **AI → Assistant** (or press Ctrl/Cmd+K → *Ask the assistant*) and type a question:

- "What blocks the web app stage?"
- "Which tasks are over budget, and why?"
- "Summarise what happened yesterday."
- "Draft a task for exporting bookmarks as CSV."

Each question runs as a short headless session with a compact, read-only briefing of the project. Conversations are stored on this machine only.

## Proposals

When an action would help, the answer carries **proposals** — cards with a title, a reason and an **Apply** button:

| Kind | Applies as |
|---|---|
| `state` | a status transition through the state machine |
| `plan_task` | a new task through the validated plan editor |
| `gate` | a gate job for a task |
| `session` | a headless session for a task |
| `note` | nothing; a note to read |

Applying runs exactly the call you could make yourself, so a refused transition is refused for the assistant too.

## Tools for the assistant

The assistant session gets every [connector](polier:mcp-connectors) enabled for the role `assistant` — by default Polier's own read-only MCP server, so it can look up details beyond its briefing.

> [!TIP]
> Ask for a plan, not an action: "What would you do next and why?" gives better proposals than "Fix it."
