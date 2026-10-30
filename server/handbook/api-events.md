# Live events

`GET /api/events` is a Server-Sent Events stream. The page uses it to refresh without polling; your tools can too.

```bash
curl -N http://127.0.0.1:8765/api/events
```

```javascript
const events = new EventSource('http://127.0.0.1:8765/api/events');
events.addEventListener('state', (event) => console.log('state', JSON.parse(event.data)));
events.addEventListener('job', (event) => console.log('job', JSON.parse(event.data)));
```

## Event types

| Event | Sent when |
|---|---|
| `ready` | the stream is connected |
| `state` | a status changed, the plan was edited, a bulk action ran, or files changed on disk |
| `job` | a gate, check or audit job started, logged or finished |
| `session` | a headless session started, progressed or ended |
| `approval` | an approval was requested, granted or denied |
| `claim` | a claim was taken or released |
| `plan` | the interview draft changed |
| `inbox` | inbox counts changed |
| `settings`, `views` | `dashboard.json` or a saved view changed |
| `intake`, `templates`, `assistant`, `automations` | the matching feature changed |
| `setup` | the first-run setup state changed |
| `lag` | the client fell behind; reload the snapshot |

The payload is JSON. Treat events as hints: on any event, re-read what you display (for example `GET /api/snapshot`).
