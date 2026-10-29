# Automations

Automations turn project state into suggestions. They never act on their own: a run is a dry run, and you apply what makes sense.

## Write a rule

Rules live in the committed `automations.json`. **Automations → Load example rules** starts you off.

```json
{
  "version": 1,
  "rules": [
    {
      "id": "failed-gate-to-rework",
      "name": "A failed gate sends the task to rework",
      "enabled": true,
      "when": { "kind": "gate_failed" },
      "actions": [
        { "type": "state", "status": "rework", "note": "A gate failed; fix it before continuing." }
      ]
    }
  ]
}
```

## Triggers

| `when.kind` | Matches |
|---|---|
| `gate_failed` | a task whose latest gate run failed |
| `task_blocked` | a blocked task |
| `budget_over` | a task over its token budget |
| `review_ready` | a task waiting for a review |
| `session_failed` | a failed headless session |
| `intake_proposed` | an open intake proposal |
| `stage_decision_pending` | a complete stage without a decision |
| `task_ready` | a task in the next wave |

Actions: `state`, `session`, `open`, `note`.

## Run and apply

**Run dry run** lists every match with its suggested actions. **Apply** sends one suggestion through the normal validated API — exactly as if you had clicked it yourself.

```bash
python3 tools/automations.py validate
python3 tools/automations.py run
```
