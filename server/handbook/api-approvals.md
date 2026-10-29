# Approvals

Request owner decisions and record the answer. Every record is a committed file in `reviews/approvals/`.

| Endpoint | Purpose |
|---|---|
| `GET /api/approvals` | all records, optionally by `status` |
| `POST /api/approvals/request` | request an approval |
| `POST /api/approvals/{id}/grant` | grant it |
| `POST /api/approvals/{id}/deny` | deny it |

## List approvals

### GET /api/approvals

| Query | Type | Description |
|---|---|---|
| `status` | string | `pending`, `granted` or `denied` |

## Request an approval

### POST /api/approvals/request

| Field | Type | Required | Description |
|---|---|---|---|
| `action` | string | yes | `new_dependency`, `scope_change`, `merge_to_base`, `release`, `reopen_done`, `protected_path`, `state_override` |
| `task` | string | no | task the decision concerns |
| `note` | string | no | what and why |
| `by` | string | no | requester, default the dashboard role |

```bash
curl -s -X POST http://127.0.0.1:8765/api/approvals/request \
  -H "X-Polier-Action: 1" -H "Content-Type: application/json" \
  -d '{"action": "new_dependency", "task": "API-01", "note": "httpx for the sync client"}'
```

```python
record = call("POST", "/api/approvals/request",
              {"action": "new_dependency", "task": "API-01", "note": "httpx for the sync client"})
```

```javascript
const record = await call('POST', '/api/approvals/request', { action: 'new_dependency', task: 'API-01' });
```

**Response**

```json
{ "id": "AP-002", "action": "new_dependency", "task": "API-01", "status": "pending", "requested_by": "lead" }
```

## Decide

### POST /api/approvals/{id}/grant

### POST /api/approvals/{id}/deny

| Field | Type | Description |
|---|---|---|
| `note` | string | the reason, recorded with the decision |
| `by` | string | decider, default `owner` |

```python
call("POST", "/api/approvals/AP-002/grant", {"note": "stdlib urllib is too thin for retries"})
```
