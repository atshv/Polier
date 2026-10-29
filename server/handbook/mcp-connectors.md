# MCP connectors

Connectors are MCP servers that Polier's headless sessions and the assistant may use as tools — a GitHub server for issues and pull requests, a browser to check the UI, a docs server. They are configured per machine, because they carry local commands and secrets.

## Add a connector

**AI → MCP → Connectors → Add connector**. Start from a preset or fill in:

| Field | Meaning |
|---|---|
| Name | lowercase; tools appear as `mcp__<name>__<tool>` |
| Transport | **Local command (stdio)**: command, arguments, environment. **Remote URL (HTTP)**: URL and headers |
| Available to | which roles get it: worker, reviewer, lead, assistant, generator |
| Description | what agents use it for |

Presets cover a remote GitHub server, a filesystem server, a fetch server and a Playwright browser. Replace the `<placeholders>` (tokens, folders) before saving.

> [!WARNING]
> Environment values and headers usually hold tokens. They are stored in the machine-local runtime folder, shown masked and never committed — but every session that gets the connector can use them. Give agents only what the task needs.

## Test it

**Test** connects once: `initialize`, then `tools/list`. You see the server name, version and its tools — or the error, such as a missing command or `HTTP 401`.

## Who gets which connector

1. A session gets every **enabled** connector whose roles include the session's role.
2. An [agent](polier:agents) that lists connectors gets only those.
3. The built-in connector `polier` is Polier's own [MCP server](polier:mcp-server). It is read-only for every role except `lead`, and only when you switch read-only off.

With Claude Code the selection is written to the session folder as `mcp.json`, passed with `--mcp-config`, and `mcp__<name>` is added to the allowed tools.

## Remote servers that need a browser login

Some hosted MCP servers use OAuth in the browser. A headless session cannot complete that login. Use a token header where the server supports it, or connect those servers in your interactive client instead.
