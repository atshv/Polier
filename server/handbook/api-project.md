# Project

Read the whole project in one call, or the parts you need.

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | version, role, board presence |
| `GET /api/config` | dashboard config, gate commands, session settings, first-run setup state |
| `PUT /api/config` | save gate commands, session settings, UI preferences |
| `GET /api/snapshot` | tasks with derived fields, stages, dispatch, counts, git |
| `GET /api/dispatch` | the dispatch plan |
| `GET /api/activity` | the activity feed |
| `GET /api/files`, `GET /api/file` | browse and preview repository files |
| `GET /api/audit` | the compliance audit |

## Get the snapshot

### GET /api/snapshot

Everything the board needs: project facts, stages, tasks with derived fields (gates passed, tokens, budget state, claim, wave), approvals, counts and git state. Cached until a project file changes.

| Query | Type | Description |
|---|---|---|
| `fresh` | `1` | rebuild even if nothing changed |

```bash
curl -s http://127.0.0.1:8765/api/snapshot | python3 -m json.tool | head -40
```

```python
snapshot = call("GET", "/api/snapshot")
for task in snapshot["tasks"]:
    print(task["id"], task["status"], f'{len(task["gates_passed"])}/{len(task["gates"])} gates')
```

```javascript
const snapshot = await call('GET', '/api/snapshot');
const ready = snapshot.tasks.filter((task) => task.wave === 0 && task.status === 'pending');
console.log(ready.map((task) => task.id));
```

**Response** (abbreviated)

```json
{
  "project": { "name": "canvas-mini", "profile": "L", "stage": 1, "base_branch": "main" },
  "stages": [{ "id": "foundation", "title": "Foundation", "complete": true, "tasks": ["F-01", "F-02"] }],
  "tasks": [{
    "id": "ENG-01", "title": "C++ scene core and unit tests", "status": "in_progress",
    "stage": "engine-spike", "gates": ["cpp-unit", "lint"], "gates_passed": ["lint"],
    "tokens": 182000, "budget": { "max": 2000000, "warn": false, "over": false },
    "claim": { "harness": "cli", "session": "me" }, "wave": null
  }],
  "dispatch": { "next_wave": ["API-01"], "blocked": [] },
  "git": { "branch": "main", "dirty": false }
}
```

## Get the dispatch plan

### GET /api/dispatch

The next wave (tasks that may start now), running attempts, blocked tasks with reasons and scope conflicts. Answers `409` while there is no `board.json`.

```bash
curl -s http://127.0.0.1:8765/api/dispatch
```

## Read the activity feed

### GET /api/activity

Run events, gate results, reviews and approvals, newest first.

| Query | Type | Description |
|---|---|---|
| `limit` | integer | number of items, default `150` |

## Read and change the local config

### GET /api/config

Machine-local settings: suggested and saved gate commands, session provider, UI preferences, read-only flag, versions, and `setup` — the first-run state described in [Settings and views](polier:api-settings).

### PUT /api/config

| Field | Type | Description |
|---|---|---|
| `gate_commands` | object | gate name → shell command |
| `session` | object | provider command, permission mode, allowed tools, model, env |
| `ui` | object | free-form UI preferences |

```bash
curl -s -X PUT http://127.0.0.1:8765/api/config \
  -H "X-Polier-Action: 1" -H "Content-Type: application/json" \
  -d '{"gate_commands": {"cpp-unit": "ctest --test-dir build --output-on-failure"}}'
```

```python
call("PUT", "/api/config", {"gate_commands": {"cpp-unit": "ctest --test-dir build"}})
```

```javascript
await call('PUT', '/api/config', { gate_commands: { 'cpp-unit': 'ctest --test-dir build' } });
```

## Browse files

### GET /api/files

Tracked files of the repository below `prefix`.

### GET /api/file

A text preview of one file, `?path=src/canvas.cpp`. Paths outside the project are refused.

## Run the audit

### GET /api/audit

Every task against the policy, runs, gates and reviews — the same report as `tools/audit.py`.
