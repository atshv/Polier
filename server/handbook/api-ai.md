# AI and integrations

Agent profiles, skills, the MCP server and connectors, and the GitHub account connection.

| Endpoint | Purpose |
|---|---|
| `GET /api/agents` | profiles (built-in until `agents.json` exists) with missing skills and connectors |
| `PUT /api/agents` | replace the list; writes `agents.json` |
| `GET /api/skills` | project skills and the shipped examples |
| `POST /api/skills/examples` | copy examples into `.claude/skills/` |
| `GET /api/skills/{id}` | one skill |
| `PUT /api/skills/{id}` | create or update a skill |
| `DELETE /api/skills/{id}` | delete a skill |
| `GET /api/mcp` | Polier's MCP server (tools, paths) and the connectors, secrets masked |
| `PUT /api/mcp/connectors/{name}` | add or update a connector (or switch the built-in `polier`) |
| `DELETE /api/mcp/connectors/{name}` | remove a connector |
| `POST /api/mcp/connectors/{name}/test` | connect once: initialize and tools/list |
| `GET /api/github/auth` | gh installed, signed in, account, scopes, login progress |
| `POST /api/github/login` | start the device login, or sign in with `token` |
| `POST /api/github/login/cancel` | cancel a running device login |
| `POST /api/github/logout` | sign gh out of github.com |

## Save the agents

### PUT /api/agents

`{ "agents": [ … ] }` replaces the whole list. Each agent:

| Field | Type | Description |
|---|---|---|
| `id` | string | lowercase, unique |
| `name` | string | 1–60 characters |
| `role` | string | `worker`, `reviewer`, `lead` |
| `description`, `instructions` | string | shown on the card / inlined into the prompt |
| `model` | string \| null | provider model override |
| `skills` | string[] | skill IDs (project or shipped example) |
| `connectors` | string[] | connector names; empty = all enabled for the role |
| `worktree` | boolean | run in a task worktree by default |

```python
call("PUT", "/api/agents", {"agents": [
    {"id": "ui-builder", "name": "UI builder", "role": "worker", "worktree": True,
     "skills": ["stay-in-scope", "test-first"], "connectors": ["browser"],
     "instructions": "UI work follows docs/design-rules.md."},
]})
```

Assign it with `POST /api/sessions` and `{"agent": "ui-builder", "task": "WEB-01"}`; see [Sessions](polier:api-sessions).

## Write a skill

### PUT /api/skills/{id}

| Field | Type | Description |
|---|---|---|
| `name` | string | 1–80 characters |
| `description` | string | when to use it, 1–300 characters |
| `body` | string | the instructions in Markdown |

```bash
curl -s -X PUT http://127.0.0.1:8765/api/skills/api-style \
  -H "X-Polier-Action: 1" -H "Content-Type: application/json" \
  -d '{"name": "API style", "description": "Use when adding an endpoint.", "body": "Return {\"error\": …} with a status code."}'
```

## Configure a connector

### PUT /api/mcp/connectors/{name}

| Field | Type | Description |
|---|---|---|
| `type` | string | `stdio` (default) or `http` |
| `command`, `args`, `env` | string, string[], object | for `stdio` |
| `url`, `headers` | string, object | for `http` |
| `roles` | string[] | `worker`, `reviewer`, `lead`, `assistant`, `generator` |
| `enabled` | boolean | default `true` |
| `description` | string | what it is for |

Secret values come back as `••••••`; send that value unchanged to keep the stored secret. For the built-in `polier` only `enabled`, `read_only` and `roles` are accepted.

```javascript
await call('PUT', '/api/mcp/connectors/browser', {
  type: 'stdio', command: 'npx', args: ['@playwright/mcp@latest'], roles: ['worker', 'reviewer'],
});
const result = await call('POST', '/api/mcp/connectors/browser/test');
console.log(result.ok ? result.tools : result.error);
```

## Connect GitHub

### POST /api/github/login

Without a body it starts the device flow and returns the one-time code:

```json
{ "auth": { "logged_in": false }, "login": { "status": "waiting", "code": "WXYZ-1234", "url": "https://github.com/login/device" } }
```

Show the code, let the user confirm on the device page, then poll `GET /api/github/auth` until `login.status` is `done` (or `failed`, `cancelled`). With `{ "token": "ghp_…" }` it signs in at once. The token goes to `gh`; Polier keeps nothing.
