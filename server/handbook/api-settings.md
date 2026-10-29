# Settings and views

Project settings live in the committed `dashboard.json`; views in `views/<id>.json`.

| Endpoint | Purpose |
|---|---|
| `GET /api/settings` | features, labels, palette, groups, `me`, local config |
| `PUT /api/settings` | merge `features`, `defaults`, replace `labels` |
| `POST /api/settings/labels` | add a label |
| `PUT /api/settings/labels/{id}` | update a label |
| `DELETE /api/settings/labels/{id}` | delete a label (`force` removes it from tasks) |
| `GET /api/filters/fields` | filter fields, operators, grouping and sort options |
| `GET /api/views` | built-in and saved views |
| `PUT /api/views/{id}` | save a view |
| `DELETE /api/views/{id}` | delete a saved view |

## Toggle features

### PUT /api/settings

```bash
curl -s -X PUT http://127.0.0.1:8765/api/settings \
  -H "X-Polier-Action: 1" -H "Content-Type: application/json" \
  -d '{"features": {"github": false}, "defaults": {"me": "rasul", "hours_per_day": 5}}'
```

Unknown top-level fields are refused with `400`.

## Add a label

### POST /api/settings/labels

| Field | Type | Description |
|---|---|---|
| `id` | string | lowercase, e.g. `risk-high` |
| `title` | string | shown on chips |
| `color` | string | palette name: `neutral`, `blue`, `green`, `amber`, `orange`, `red`, `violet`, `teal` |
| `group` | string | `type`, `risk`, `origin`, `area`, `theme` or `custom` |

```python
call("POST", "/api/settings/labels", {"id": "perf", "title": "Performance", "color": "teal", "group": "area"})
```

## Save a view

### PUT /api/views/{id}

| Field | Type | Description |
|---|---|---|
| `name` | string | display name |
| `kind` | string | `board` or `table` |
| `filters` | object[] | conditions `{ "field", "op", "value" }` |
| `group_by` | string | e.g. `stage` |
| `sort` | object | `{ "field": "estimate_hours", "dir": "desc" }` |

```javascript
await call('PUT', '/api/views/risky-open', {
  name: 'Risky and open', kind: 'board',
  filters: [{ field: 'label', op: 'any_of', value: ['risk-high'] },
            { field: 'status', op: 'none_of', value: ['done'] }],
  group_by: 'stage',
});
```

`GET /api/filters/fields` lists every field with its kind and the operators it accepts.
