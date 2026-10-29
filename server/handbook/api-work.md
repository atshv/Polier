# Your work

The owner's queue, the inbox, effort and bulk actions.

| Endpoint | Purpose |
|---|---|
| `GET /api/me` | Your Work: counts, my tasks, reviews, approvals, blocked, budget, ready, sessions |
| `GET /api/inbox` | inbox items and counts |
| `POST /api/inbox/read` | mark items read or unread |
| `GET /api/worklog` | project or task worklog |
| `POST /api/bulk` | one action on many tasks |

## Read the inbox

### GET /api/inbox

| Query | Type | Description |
|---|---|---|
| `unread` | `1` | only unread items |

```python
inbox = call("GET", "/api/inbox?unread=1")
for item in inbox["items"]:
    print(item["severity"], item["title"])
```

### POST /api/inbox/read

| Field | Type | Description |
|---|---|---|
| `ids` | string[] | item IDs |
| `read` | boolean | default `true`; `false` marks unread |
| `all` | boolean | mark every current item |

## Effort

### GET /api/worklog

Without parameters: project and stage sums plus one row per task (estimate, actual hours, tokens, sessions). With `?task=ENG-01`: that task's attempts, gate runs, sessions and usage.

## Bulk actions

### POST /api/bulk

| Field | Type | Description |
|---|---|---|
| `action` | string | `state`, `claim`, `release`, `labels`, `estimate` |
| `tasks` | string[] | up to 100 task IDs |
| `status`, `note` | string | for `state` |
| `labels` | string[] | for `labels` (replaces the task's labels) |
| `estimate_hours` | number \| null | for `estimate` |

```bash
curl -s -X POST http://127.0.0.1:8765/api/bulk \
  -H "X-Polier-Action: 1" -H "Content-Type: application/json" \
  -d '{"action": "labels", "tasks": ["WEB-01", "WEB-02"], "labels": ["feature"]}'
```

```javascript
const result = await call('POST', '/api/bulk', { action: 'state', tasks: ['ENG-02', 'API-01'], status: 'blocked', note: 'toolchain' });
result.results.filter((entry) => !entry.ok).forEach((entry) => console.warn(entry.task, entry.error));
```

**Response**

```json
{
  "action": "state",
  "results": [{ "task": "ENG-02", "ok": true }, { "task": "API-01", "ok": false, "error": "…" }],
  "ok_count": 1,
  "failed_count": 1
}
```
