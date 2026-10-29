# Planning views

Read models behind Timeline, Cycles, Modules, Coverage and Analytics. All are `GET`, derived on request from the board, the run records and the worklog.

| Endpoint | Returns |
|---|---|
| `GET /api/timeline` | days and weeks, stage lanes with scheduled task bars (`start`, `end`, `critical`, `explicit`, `overdue`), the critical path and unscheduled tasks |
| `GET /api/cycles` | each stage with goal, exit gates, progress, decision, effort and a burndown series |
| `GET /api/modules` | packages with tasks, status counts, health, docs and contracts |
| `GET /api/coverage` | requirements from `docs/quality.md` with linked tasks, evidence and state |
| `GET /api/analytics` | completion, throughput per week, cycle time, gate pass rate, rework, effort, tokens |

## Example: overdue tasks

### GET /api/timeline

```python
timeline = call("GET", "/api/timeline")
for stage in timeline["stages"]:
    for bar in stage["tasks"]:
        if bar["overdue"]:
            print(bar["id"], bar["start"], "→", bar["end"])
```

## Example: uncovered requirements

### GET /api/coverage

```javascript
const coverage = await call('GET', '/api/coverage');
const gaps = coverage.requirements.filter((req) => req.state === 'missing' || req.state === 'open');
console.table(gaps.map((req) => ({ id: req.id, state: req.state })));
```

Scheduling uses `estimate_hours` (or complexity × 2 h) at `dashboard.json` → `defaults.hours_per_day`.
