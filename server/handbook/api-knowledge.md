# Knowledge

Pages, search, intake and task templates.

| Endpoint | Purpose |
|---|---|
| `GET /api/pages` | the index: collections, pages, counts |
| `GET /api/page` | one page: text, backlinks, history (`?path=`, optional `&ref=`) |
| `GET /api/page/history` | git history of a page |
| `GET /api/pages/search` | full-text search (`?q=`, `&limit=`) |
| `GET /api/pages/favorites`, `PUT /api/pages/favorites` | local favorites |
| `GET /api/handbook` | this handbook: guides and API reference |
| `GET /api/intake`, `POST /api/intake` | list (`?status=`) and create proposals |
| `GET /api/intake/{id}`, `PATCH /api/intake/{id}` | read and edit one proposal |
| `POST /api/intake/{id}/accept` | accept into a pending task |
| `POST /api/intake/{id}/reject` | reject with a reason |
| `GET /api/task-templates`, `POST /api/task-templates` | list and save templates |
| `DELETE /api/task-templates/{id}` | delete a template |

## Search the docs

### GET /api/pages/search

```bash
curl -s "http://127.0.0.1:8765/api/pages/search?q=tokens&limit=5"
```

```python
for hit in call("GET", "/api/pages/search?q=release")["results"]:
    print(hit["score"], hit["path"], hit["snippet"])
```

## Read a page at a revision

### GET /api/page

```javascript
const page = await call('GET', '/api/page?path=ARCHITECTURE.md&ref=HEAD~3');
console.log(page.title, page.words, page.backlinks.length);
```

## Propose and accept

### POST /api/intake

| Field | Type | Description |
|---|---|---|
| `title` | string | required |
| `description` | string | Markdown |
| `kind` | string | `idea`, `issue`, `request`, `question` |
| `priority` | string | `low`, `medium`, `high` |
| `links` | string[] | URLs or paths |

### POST /api/intake/{id}/accept

| Field | Type | Description |
|---|---|---|
| `stage` | string | stage of the new task |
| `template` | string | optional task template |
| `task` | object | any task fields to set (scope, gates, labels, estimate …) |
| `note` | string | decision note |

```python
result = call("POST", "/api/intake/IN-004/accept",
              {"stage": "surface", "template": "ui-view", "note": "fits the surface stage"})
print("created", result["task"]["id"])
```

### POST /api/intake/{id}/reject

`{ "note": "out of scope for v1" }` — a reason is required.

## Save a template from a task

### POST /api/task-templates

`{ "from_task": "ENG-01", "id": "cpp-module", "name": "C++ module with tests" }` — or send the template fields directly.
