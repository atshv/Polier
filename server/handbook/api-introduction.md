# API introduction

The dashboard is a small JSON API on your machine. Everything the page does goes through it, so your scripts, CI jobs and agents can do the same: read the board, move tasks, run gates, start sessions.

## Base URL

```text
http://127.0.0.1:8765
```

The port is whatever you passed to `tools/serve.py --port`. The server binds to loopback unless you choose another `--host`; a non-loopback bind requires a token.

## Conventions

- Requests and responses are JSON (`Content-Type: application/json`), UTF-8.
- `GET` reads, `POST` / `PUT` / `PATCH` / `DELETE` change something and need the `X-Polier-Action: 1` header.
- Times are ISO 8601 in UTC, dates are `YYYY-MM-DD`.
- IDs are the ones from your files: task `ENG-01`, approval `AP-001`, intake `IN-001`, label `risk-high`.
- Every write goes through the same core functions and validation as the CLI, and lands in the same files.

## A first request

```bash
curl -s http://127.0.0.1:8765/api/health
```

```python
import json, urllib.request

with urllib.request.urlopen("http://127.0.0.1:8765/api/health") as res:
    print(json.load(res))
```

```javascript
const res = await fetch('http://127.0.0.1:8765/api/health');
console.log(await res.json());
```

**Response**

```json
{
  "ok": true,
  "version": "2.7.0",
  "role": "lead",
  "board_present": true,
  "root": "/home/me/canvas-mini",
  "started": "2026-10-29T09:12:44+00:00",
  "read_only": false
}
```

## A small client

The examples in this reference use these two helpers. They need nothing beyond the standard library or the browser.

```python
import json, os, urllib.request

BASE = "http://127.0.0.1:8765"
TOKEN = os.environ.get("POLIER_DASHBOARD_TOKEN")

def call(method, path, body=None):
    headers = {"Content-Type": "application/json"}
    if method != "GET":
        headers["X-Polier-Action"] = "1"
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req) as res:
        return json.load(res)
```

```javascript
const BASE = 'http://127.0.0.1:8765';
const TOKEN = null; // set when the server runs with --token

async function call(method, path, body) {
  const headers = { 'Content-Type': 'application/json' };
  if (method !== 'GET') headers['X-Polier-Action'] = '1';
  if (TOKEN) headers.Authorization = `Bearer ${TOKEN}`;
  const res = await fetch(BASE + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const data = await res.json();
  if (!res.ok) throw Object.assign(new Error(data.error), { status: res.status, details: data.details });
  return data;
}
```

## Endpoint groups

| Group | Covers |
|---|---|
| [Project](polier:api-project) | health, config, snapshot, dispatch, activity, files, audit |
| [Tasks](polier:api-tasks) | task detail, status transitions, claims, gate logs |
| [Jobs and gates](polier:api-jobs) | gate, check and audit runs with live logs |
| [Sessions](polier:api-sessions) | headless agent sessions |
| [Approvals](polier:api-approvals) | request, grant, deny |
| [Plan](polier:api-plan) | interview, generator, tasks, stages |
| [Settings and views](polier:api-settings) | features, labels, filters, saved views |
| [Your work](polier:api-work) | Your Work, inbox, worklog, bulk actions |
| [Planning views](polier:api-planning) | timeline, cycles, modules, coverage, analytics |
| [Knowledge](polier:api-knowledge) | pages, search, intake, task templates |
| [Intelligence](polier:api-intelligence) | assistant, automations, GitHub |
| [AI and integrations](polier:api-ai) | agents, skills, MCP server and connectors, GitHub account |
