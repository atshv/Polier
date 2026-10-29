# Tasks

Read one task in depth, move it through the state machine and manage its claim.

| Endpoint | Purpose |
|---|---|
| `GET /api/tasks/{id}` | brief, gates, records, events, review, worklog |
| `POST /api/tasks/{id}/state` | status transition |
| `POST /api/tasks/{id}/claim` | take the claim |
| `DELETE /api/tasks/{id}/claim` | release the claim |
| `GET /api/claims` | all live claims |
| `GET /api/tasks/{id}/logs/{log}` | one gate log |

## Get a task

### GET /api/tasks/{id}

```bash
curl -s http://127.0.0.1:8765/api/tasks/ENG-01
```

```python
task = call("GET", "/api/tasks/ENG-01")
print(task["brief"]["text"][:300])
```

```javascript
const task = await call('GET', '/api/tasks/ENG-01');
console.log(task.review?.verdict ?? 'no verdict yet');
```

Answers `404` for an unknown task.

## Change the status

### POST /api/tasks/{id}/state

Runs the same checks as `tools/state.py set`: dependencies, gate records, review verdict, attempt and round limits.

| Field | Type | Required | Description |
|---|---|---|---|
| `status` | string | yes | target status, e.g. `in_progress`, `verifying`, `review`, `done` |
| `note` | string | for `rework`, `blocked`, `failed` | why |
| `actor` | string | no | recorded actor, default `lead` |
| `force` | boolean | no | lead override; recorded as such |

```bash
curl -s -X POST http://127.0.0.1:8765/api/tasks/ENG-01/state \
  -H "X-Polier-Action: 1" -H "Content-Type: application/json" \
  -d '{"status": "verifying"}'
```

```python
try:
    call("POST", "/api/tasks/ENG-01/state", {"status": "review"})
except urllib.error.HTTPError as err:
    problem = json.load(err)
    print(problem["error"], problem["details"]["errors"])
```

```javascript
try {
  await call('POST', '/api/tasks/ENG-01/state', { status: 'blocked', note: 'waits for the WASM toolchain' });
} catch (err) {
  if (err.status === 409) console.log(err.details.errors, err.details.actions);
}
```

**Response**

```json
{ "ok": true, "result": { "ok": true, "task": "ENG-01", "from": "in_progress", "to": "verifying" }, "snapshot": { "…": "…" } }
```

A refused transition answers `409` with `details.errors` and `details.actions`; see [Errors](polier:api-errors).

## Claim a task

### POST /api/tasks/{id}/claim

| Field | Type | Description |
|---|---|---|
| `harness` | string | who holds it, default `dashboard` |
| `session` | string | session id, default `dashboard-<pid>` |
| `worktree` | string | optional worktree path |
| `slot` | integer | optional runtime slot |

Answers `409` when another session holds the claim.

### DELETE /api/tasks/{id}/claim

Releases the claim: `{ "task": "ENG-01", "released": true }`.

## Read a gate log

### GET /api/tasks/{id}/logs/{log}

`{ "log": "cpp-unit-1.log", "text": "…" }` from `reviews/evidence/`.
