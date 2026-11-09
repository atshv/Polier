# Environments: canvas-mini

> Variable names only — never values. Local ports come from `.polier-slot`: port = 4100 + 50 · slot + service offset (`web` +0, `api` +1).

## Checklist

| Environment | URL | Required variables (names only) | Set in | Who may change | Smoke check |
| --- | --- | --- | --- | --- | --- |
| local | `http://localhost:4100` | `PORT`, `SYNC_PORT`, `NEXT_PUBLIC_SYNC_URL` | `.env.local` (gitignored; names in `.env.example`) | developer | `python3 .generator/tools/smoke.py --url http://localhost:4100 --expect-status 200 --path /` |
| preview | `https://canvas-mini-preview.example.com` | `PREVIEW_TOKEN`, `SYNC_SECRET`, `NEXT_PUBLIC_SYNC_URL` | CI secret + hosting dashboard | owner | `python3 .generator/tools/smoke.py --url https://canvas-mini-preview.example.com --expect-status 200 --path / --header "Authorization: env:PREVIEW_TOKEN"` |
| staging | `https://staging.canvas-mini.example.com` | `SYNC_SECRET`, `NEXT_PUBLIC_SYNC_URL` | CI secret + hosting dashboard | owner | `python3 .generator/tools/smoke.py --url https://staging.canvas-mini.example.com --expect-status 200 --path /` |
| production | `https://canvas-mini.example.com` | same names as staging, different values | CI secret + hosting dashboard | owner only | `python3 .generator/tools/smoke.py --url https://canvas-mini.example.com --expect-status 200 --path /` |

## Where values live

- **Local:** `.env.local` in the project root, gitignored. `.env.example` lists names only. Ports and service URLs come from `.polier-slot`.
- **CI:** the provider's secret store; workflows reference names, never echo values.
- **Preview, staging, production:** hosting dashboard or platform secret store, one value per environment.
- Never in the repo, a brief, a screenshot, a log or a chat.

## Rules

- A variable name missing from this table, or missing at runtime, is a deployment failure: add it here and in the secret store, redeploy, then smoke again. Do not simply retry.
- `smoke` is the post-deploy gate. Run it after every preview, staging and production deployment; it writes a gate record and exit 0 is required.
- Every environment row carries an `http(s)` smoke URL. A row without one is an incomplete checklist and blocks release.
- Add or rename a variable in the same task as the code that uses it, for local, preview, staging and production.
- Never touch slot 0's data; a second worktree uses the next slot (`python3 .generator/tools/slot.py show`).
