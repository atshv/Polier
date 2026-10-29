# AI in Polier

Polier puts AI to work in five places. All of them run on your machine, use the provider you configured (Claude Code by default) and stay inside the same rules as a human: the write guard, the state machine and the evidence records.

| Feature | What it does | Where |
|---|---|---|
| [Assistant](polier:assistant) | answers questions about the project and proposes actions you confirm | **AI → Assistant** |
| [Agents](polier:agents) | reusable profiles you assign to tasks; each run is a headless session | **AI → Agents** |
| [Skills](polier:skills) | reusable instructions agents follow when they apply | **AI → Skills** |
| [MCP server](polier:mcp-server) | Polier's board as tools for Claude Code, Claude Desktop, Cursor or VS Code | **AI → MCP** |
| [MCP connectors](polier:mcp-connectors) | other MCP servers your agents may use: GitHub, a browser, docs | **AI → MCP → Connectors** |

## How the pieces fit

1. You describe *who* works with an **agent**: role, model, instructions.
2. You describe *how* they work with **skills**: test first, stay in scope, review checklist.
3. You decide *what else they may reach* with **connectors**.
4. You **assign** the agent to a task. Polier starts a session, claims the task and inlines the agent's instructions and skills into the prompt.
5. The **assistant** watches the whole project and suggests the next step; nothing happens until you click **Apply**.
6. Your own AI client sees the same board through the **MCP server**.

## Safety model

> [!IMPORTANT]
> AI never gets more rights than the role it runs as. A worker can only write inside its task's `scope.write`; status changes go through the state machine; "done" needs recorded gates and a passing review.

- **Explicit start.** Sessions only start when you start them, from the dashboard, the CLI or an applied proposal.
- **Confirmed proposals.** The assistant cannot write. Its proposals run through the validated API after your click.
- **Local secrets.** Connector tokens and environment values live in the machine-local runtime folder, are masked in the UI and never committed.
- **Read-only by default.** Agents get Polier's own MCP server read-only; only lead sessions may use its write tools, and only if you switch read-only off.
- **Auditable.** Every session keeps its prompt, settings, MCP config and transcript under `<git-common-dir>/polier/dashboard/sessions/`.
