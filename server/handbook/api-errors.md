# Errors

Errors use HTTP status codes and one JSON shape:

```json
{
  "error": "transition refused",
  "details": {
    "errors": ["ENG-02 depends on ENG-01 (in_progress)"],
    "actions": ["python3 tools/state.py show ENG-01"],
    "detail": "…"
  }
}
```

`details` is optional and depends on the endpoint.

## Status codes

| Code | Meaning | Typical cause |
|---|---|---|
| `200` | success | — |
| `400` | invalid request | missing field, bad JSON, failed validation (cycle in dependencies, unknown label) |
| `401` | unauthenticated | token required but missing or wrong |
| `403` | forbidden | missing `X-Polier-Action`, cross-origin write, read-only mode, non-loopback host without token |
| `404` | not found | unknown task, job, session, page, intake entry or route |
| `405` | method not allowed | e.g. `DELETE /api/config` |
| `409` | conflict | a refused status transition, a claim held by another session, no `board.json` yet |
| `413` | payload too large | request body over the limit |
| `500` | internal error | a bug — the server log has the traceback |

## Refused transitions

A `409` from `POST /api/tasks/<id>/state` lists the reasons in `details.errors` and the commands that produce the missing proof in `details.actions` — exactly what `tools/state.py` prints. Show them to the user instead of retrying.

## Bulk results

`POST /api/bulk` returns `200` even when some tasks fail; check `failed_count` and each `results[].error`.
