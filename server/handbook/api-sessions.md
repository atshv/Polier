# Sessions

Start headless agent sessions with the configured provider, follow their transcript and stop them.

| Endpoint | Purpose |
|---|---|
| `GET /api/sessions` | all sessions |
| `POST /api/sessions` | start one |
| `GET /api/sessions/{id}` | one session |
| `GET /api/sessions/{id}/log` | its transcript |
| `POST /api/sessions/{id}/stop` | stop it |

## Start a session

### POST /api/sessions

| Field | Type | Description |
|---|---|---|
| `task` | string | task ID; omit for a free session |
| `role` | string | `worker` (default), `reviewer`, `lead` |
| `note` | string | operator note appended to the prompt |
| `prompt` | string | a full prompt instead of the composed one |
| `worktree` | boolean | run in a fresh task worktree |
| `model` | string | provider model override |
| `env` | object | extra environment variables |

```bash
curl -s -X POST http://127.0.0.1:8765/api/sessions \
  -H "X-Polier-Action: 1" -H "Content-Type: application/json" \
  -d '{"task": "ENG-01", "role": "reviewer", "note": "focus on acceptance A3"}'
```

```python
session = call("POST", "/api/sessions", {"task": "ENG-01", "role": "worker", "worktree": True})
print(session["id"], session["status"])
```

```javascript
const session = await call('POST', '/api/sessions', { task: 'ENG-01', role: 'worker' });
```

The session takes the task's claim and releases it when it ends; tokens reported by the provider are recorded in `runs/<ID>.json`.

## Follow the transcript

### GET /api/sessions/{id}/log

Same paging as job logs: `offset` and `limit` in, `text` and `next` out.

### POST /api/sessions/{id}/stop

Ends the provider process. The attempt is recorded as stopped.
