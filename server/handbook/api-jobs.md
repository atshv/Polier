# Jobs and gates

Long-running checks run as jobs: the call returns at once, the log streams while it runs, and gate jobs write the same evidence records as `tools/gate.py`.

| Endpoint | Purpose |
|---|---|
| `POST /api/jobs/gate` | run one gate for a task |
| `POST /api/jobs/check` | run `tools/check.py` |
| `POST /api/jobs/audit` | run `tools/audit.py` |
| `GET /api/jobs` | all jobs |
| `GET /api/jobs/{id}` | one job |
| `GET /api/jobs/{id}/log` | its log |
| `POST /api/jobs/{id}/stop` | stop it |

## Run a gate

### POST /api/jobs/gate

| Field | Type | Required | Description |
|---|---|---|---|
| `task` | string | yes | task ID |
| `name` | string | yes | gate name from the task |
| `command` | string | no | shell command; defaults to the configured command for `name` |
| `timeout` | integer | no | seconds, default `1800` |
| `slot` | integer | no | runtime slot for ports and databases |

```bash
curl -s -X POST http://127.0.0.1:8765/api/jobs/gate \
  -H "X-Polier-Action: 1" -H "Content-Type: application/json" \
  -d '{"task": "ENG-01", "name": "cpp-unit"}'
```

```python
job = call("POST", "/api/jobs/gate", {"task": "ENG-01", "name": "cpp-unit"})
print(job["id"], job["status"])
```

```javascript
const job = await call('POST', '/api/jobs/gate', { task: 'ENG-01', name: 'cpp-unit' });
```

Answers `400` when no command is configured for the gate.

## Follow a job

### GET /api/jobs/{id}/log

| Query | Type | Description |
|---|---|---|
| `offset` | integer | byte offset to continue from |
| `limit` | integer | max bytes, default `262144` |

The response carries `text`, `next` (the offset for the following call), `size` and the job `status`. Poll with `next` until the job's status is `pass`, `fail` or `error`, or listen for `job` events on the [event stream](polier:api-events).

```python
import time

offset = 0
while True:
    chunk = call("GET", f"/api/jobs/{job['id']}/log?offset={offset}")
    print(chunk["text"], end="")
    offset = chunk["next"]
    if chunk["status"] != "running":
        break
    time.sleep(1)
```

### POST /api/jobs/{id}/stop

Stops a running job; the gate is recorded as failed.
