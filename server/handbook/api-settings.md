# Settings and views

Project settings live in the committed `dashboard.json`; views in `views/<id>.json`.

| Endpoint | Purpose |
|---|---|
| `GET /api/settings` | features, labels, palette, groups, `me`, local config |
| `PUT /api/settings` | merge `features`, `defaults`, replace `labels` |
| `POST /api/settings/labels` | add a label |
| `PUT /api/settings/labels/{id}` | update a label |
| `DELETE /api/settings/labels/{id}` | delete a label (`force` removes it from tasks) |
| `GET /api/filters/fields` | filter fields, operators, grouping and sort options |
| `GET /api/views` | built-in and saved views |
| `PUT /api/views/{id}` | save a view |
| `DELETE /api/views/{id}` | delete a saved view |
| `GET /api/setup` | first-run state, the chosen provider and the available providers |
| `POST /api/setup` | record `complete`, `skip` or `reset` |

## Toggle features

### PUT /api/settings

```bash
curl -s -X PUT http://127.0.0.1:8765/api/settings \
  -H "X-Polier-Action: 1" -H "Content-Type: application/json" \
  -d '{"features": {"github": false}, "defaults": {"me": "rasul", "hours_per_day": 5}}'
```

Unknown top-level fields are refused with `400`.

## Add a label

### POST /api/settings/labels

| Field | Type | Description |
|---|---|---|
| `id` | string | lowercase, e.g. `risk-high` |
| `title` | string | shown on chips |
| `color` | string | palette name: `neutral`, `blue`, `green`, `amber`, `orange`, `red`, `violet`, `teal` |
| `group` | string | `type`, `risk`, `origin`, `area`, `theme` or `custom` |

```python
call("POST", "/api/settings/labels", {"id": "perf", "title": "Performance", "color": "teal", "group": "area"})
```

## Save a view

### PUT /api/views/{id}

| Field | Type | Description |
|---|---|---|
| `name` | string | display name |
| `kind` | string | `board` or `table` |
| `filters` | object[] | conditions `{ "field", "op", "value" }` |
| `group_by` | string | e.g. `stage` |
| `sort` | object | `{ "field": "estimate_hours", "dir": "desc" }` |

```javascript
await call('PUT', '/api/views/risky-open', {
  name: 'Risky and open', kind: 'board',
  filters: [{ field: 'label', op: 'any_of', value: ['risk-high'] },
            { field: 'status', op: 'none_of', value: ['done'] }],
  group_by: 'stage',
});
```

`GET /api/filters/fields` lists every field with its kind and the operators it accepts.

## Read the first-run setup

### GET /api/setup

The machine-local setup state, the chosen provider and the providers the page offers. `GET /api/config` returns the same `state` under `setup`.

```bash
curl -s http://127.0.0.1:8765/api/setup
```

**Response** (abbreviated)

```json
{
  "state": { "version": 1, "status": "pending", "updated_at": null },
  "provider": {
    "id": "claude", "command": ["claude"], "model": null,
    "installed": true, "path": "/opt/homebrew/bin/claude",
    "signed_in": true, "auth_method": "claude.ai",
    "login_command": "claude auth login", "models": ["opus", "sonnet", "haiku"]
  },
  "providers": [
    { "id": "claude", "label": "Claude Code", "command": ["claude"],
      "login_command": "claude auth login", "models": ["opus", "sonnet", "haiku"], "hint": "…" },
    { "id": "custom", "label": "Custom command", "command": null,
      "login_command": null, "models": [], "hint": "…" }
  ],
  "board_present": true
}
```

| Field | Type | Description |
|---|---|---|
| `state.status` | string | `pending`, `done` or `skipped`; `pending` opens the wizard on the next fresh start (a machine whose runtime config did not exist, or after `reset`) |
| `state.updated_at` | string \| null | ISO 8601 UTC timestamp of the last change |
| `provider.id` | string | `claude` or `custom` |
| `provider.command` | string[] | the provider command; always a non-empty array — a custom provider without a saved command falls back to `["claude"]` |
| `provider.model` | string \| null | the `--model` override; `null` is the provider default |
| `provider.installed` | boolean | the command is on `PATH` |
| `provider.path` | string \| null | resolved path of the command |
| `provider.signed_in` | boolean \| null | `true` signed in, `false` signed out for the Claude Code CLI; `null` only when the check cannot run (custom provider, CLI not installed, unreadable or timed-out answer) |
| `provider.auth_method` | string \| null | the login kind the CLI reports |
| `provider.login_command` | string \| null | the copyable command, e.g. `claude auth login` |
| `provider.models` | string[] | suggested model ids |
| `providers` | object[] | the choices: Claude Code and a custom command |
| `board_present` | boolean | whether the project has a `board.json` |

An existing dashboard runtime that has no setup record reads as `skipped`, so an upgrade never opens the wizard by itself; it stays reachable from **Setup** and **Settings**. A signed-out Claude Code CLI exits non-zero but still prints its JSON answer, so it reads as `signed_in: false`; `null` means the state could not be determined.

## Finish or reset the setup

### POST /api/setup

| Field | Type | Description |
|---|---|---|
| `action` | string | `complete`, `skip` or `reset` |

`complete` and `skip` stop the automatic open; `reset` sets the state back to `pending`. The response is the same payload as `GET /api/setup`. A missing action answers `400` (`action is required`), an unknown one `400`, and a read-only dashboard `403`.

```bash
curl -s -X POST http://127.0.0.1:8765/api/setup \
  -H "X-Polier-Action: 1" -H "Content-Type: application/json" \
  -d '{"action": "skip"}'
```
