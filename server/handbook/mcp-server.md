# Polier MCP server

The Model Context Protocol (MCP) lets AI clients call tools. Polier ships an MCP server, so your own AI client — Claude Code, Claude Desktop, Cursor, VS Code or any MCP host — can read the board and, if you allow it, act on it.

## Connect a client

**AI → MCP → Polier MCP server** shows ready-to-paste configuration with the paths of this machine and project. Pick your client:

```bash
claude mcp add polier -- python3 /path/to/Polier/tools/mcp.py --root /path/to/project --read-only
```

```json
{
  "mcpServers": {
    "polier": {
      "command": "python3",
      "args": ["/path/to/Polier/tools/mcp.py", "--root", "/path/to/project", "--read-only"]
    }
  }
}
```

| Client | Where the JSON goes |
|---|---|
| Claude Code | the `claude mcp add` command above |
| Claude Desktop | Settings → Developer → Edit Config (`claude_desktop_config.json`) |
| Cursor | `.cursor/mcp.json` in the project |
| VS Code | `.vscode/mcp.json` in the project, under `servers` with `"type": "stdio"` |

**Test the server** starts it once, performs the MCP handshake and lists its tools.

## Read-only or not

With `--read-only` every write tool is refused. Without it, the client may also change status, run gates and take claims — through the same validated paths as the dashboard. Start read-only; drop the flag only for a lead session you trust.

## Tools

The table on the page lists every tool with *read* or *write*. The most used:

| Tool | Use it to |
|---|---|
| `polier_dispatch` | ask what may start now and what blocks the rest |
| `polier_task` | read one task with brief, gates, review and events |
| `polier_me`, `polier_inbox` | see what needs the owner |
| `polier_pages_search`, `polier_page` | search and read the project docs |
| `polier_state_set` | move a task (write) |
| `polier_gate` | run a gate and record it (write) |

## Transport

`tools/mcp.py` speaks MCP over stdio (newline-delimited JSON-RPC 2.0) and needs only the Python standard library. The client starts it; there is no port and no network listener.
