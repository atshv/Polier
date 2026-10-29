# Plan

The interview, the generator and every edit of the board. Edits are validated (schema, dependency cycles, labels) and written atomically.

| Endpoint | Purpose |
|---|---|
| `GET /api/plan` | interview draft and status |
| `PUT /api/plan/answers` | save interview answers |
| `POST /api/plan/generator` | start the generator session |
| `POST /api/plan/approve` | validate and approve the plan |
| `POST /api/plan/tasks` | create a task |
| `PATCH /api/plan/tasks/{id}` | update a task |
| `DELETE /api/plan/tasks/{id}` | delete a task |
| `POST /api/plan/stages/{id}/decision` | set a stage decision |
| `POST /api/plan/stages/{id}/move` | reorder stages |

## Create a task

### POST /api/plan/tasks

| Field | Type | Description |
|---|---|---|
| `title`, `goal` | string | required |
| `stage` | string | stage ID, default the first stage |
| `id` | string | optional; suggested from the stage otherwise |
| `scope_write`, `scope_read` | string[] | allowed paths |
| `acceptance` | string[] | acceptance criteria IDs |
| `gates` | string[] | gate names |
| `depends_on` | string[] | task IDs |
| `labels` | string[] | label IDs from `dashboard.json` |
| `estimate_hours` | number | planning estimate |
| `planned_start`, `target` | date | optional fixed dates |
| `template` | string | apply a task template first |

```bash
curl -s -X POST http://127.0.0.1:8765/api/plan/tasks \
  -H "X-Polier-Action: 1" -H "Content-Type: application/json" \
  -d '{"title": "CSV export", "goal": "Export bookmarks as CSV.", "stage": "surface",
       "scope_write": ["src/export/"], "acceptance": ["A1"], "gates": ["unit"], "labels": ["feature"]}'
```

```python
task = call("POST", "/api/plan/tasks", {
    "template": "cpp-module", "title": "Colour helper", "goal": "RGB/HSL conversion.",
    "stage": "engine-spike", "estimate_hours": 3,
})
```

```javascript
const task = await call('POST', '/api/plan/tasks', {
  title: 'CSV export', goal: 'Export bookmarks as CSV.', stage: 'surface',
  scope_write: ['src/export/'], acceptance: ['A1'], gates: ['unit'],
});
```

## Update a task

### PATCH /api/plan/tasks/{id}

Send only the fields to change; `null` clears `estimate_hours`, `planned_start` and `target`.

```python
call("PATCH", "/api/plan/tasks/WEB-02", {"labels": ["feature"], "target": "2026-11-07"})
```

## Delete a task

### DELETE /api/plan/tasks/{id}

Only `pending`, `blocked` and `failed` tasks; dependants must be updated first.

## Stage decisions

### POST /api/plan/stages/{id}/decision

`{ "decision": "continue" }` — or `stop`, `pending`.

### POST /api/plan/stages/{id}/move

`{ "delta": -1 }` moves the stage one place up.

## Interview and generator

### PUT /api/plan/answers

`{ "mode": "greenfield", "answers": { "name": "…", "goal": "…" } }` saves the draft locally.

### POST /api/plan/generator

Composes the generator prompt from the answers and starts a `generator` session. Returns `{ "session": {…}, "prompt_path": "…" }`.

### POST /api/plan/approve

Validates the generated board and records the approval.
