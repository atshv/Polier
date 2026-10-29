# Intelligence

The assistant, automations and the GitHub panel.

| Endpoint | Purpose |
|---|---|
| `GET /api/assistant` | conversations |
| `POST /api/assistant/chat` | ask a question (new or existing conversation) |
| `GET /api/assistant/{id}`, `DELETE /api/assistant/{id}` | read or delete a conversation |
| `POST /api/assistant/{id}/cancel` | cancel a running answer |
| `POST /api/assistant/apply` | apply one proposal after confirmation |
| `GET /api/automations`, `PUT /api/automations` | read and save `automations.json` |
| `POST /api/automations/run` | dry run: matches and suggested actions |
| `GET /api/github` | open PRs and workflow runs mapped to tasks (`?force=1` skips the cache) |

## Ask the assistant

### POST /api/assistant/chat

| Field | Type | Description |
|---|---|---|
| `message` | string | the question |
| `conversation_id` | string | continue a conversation |

The answer is produced by a provider session in the background; while it runs, the conversation carries a `pending` object. Poll `GET /api/assistant/{id}` (or listen for `assistant` events) until `pending` is empty.

```python
import time

conversation = call("POST", "/api/assistant/chat", {"message": "What blocks the web app stage?"})
while True:
    conversation = call("GET", f"/api/assistant/{conversation['id']}")
    if not conversation.get("pending"):
        answer = conversation["messages"][-1]
        print(answer["content"])
        for proposal in answer["proposals"]:
            print("proposal:", proposal["kind"], proposal["title"])
        break
    time.sleep(1)
```

## Apply a proposal

### POST /api/assistant/apply

Proposals have a `kind` — `state`, `plan_task`, `gate`, `session` or `note` — and a `payload`. Applying one runs it through the validated API; a refused transition answers `409` like a direct call.

```javascript
await call('POST', '/api/assistant/apply', {
  conversation_id: conversation.id,
  proposal: { kind: 'state', title: 'Unblock ENG-02', payload: { task: 'ENG-02', status: 'in_progress' } },
});
```

## Run the automations

### POST /api/automations/run

A read: allowed without the action header and in read-only mode. Returns each rule's matches with suggested actions; nothing is executed.

```bash
curl -s -X POST http://127.0.0.1:8765/api/automations/run
```
