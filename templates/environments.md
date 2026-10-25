# Environments: <Project name>

> Operations template. Copy to `docs/environments.md`; keep the environments the project deploys. Variable names only — never values.

## Checklist

| Environment | URL | Required variables (names only) | Set in | Who may change | Smoke check |
| --- | --- | --- | --- | --- | --- |
| local | `http://localhost:<slot-port>` | `DATABASE_URL`, `<APP>_PUBLIC_URL` | local `.env` (gitignored; names in `.env.example`) | developer | `python3 <package>/tools/smoke.py --url http://localhost:<slot-port> --expect-status 200 --path /` |
| preview | `https://<project>-git-<branch>.<host>` | `DATABASE_URL`, `PREVIEW_TOKEN` | CI secret + hosting dashboard | owner | `python3 <package>/tools/smoke.py --url https://<preview-host> --expect-status 200 --path /login --path / --header "Authorization: env:PREVIEW_TOKEN"` |
| staging | `https://<staging-host>` | `DATABASE_URL`, `<AUTH_SECRET>`, `<PUBLIC_BASE_URL>` | CI secret + hosting dashboard | owner | `python3 <package>/tools/smoke.py --url https://<staging-host> --expect-status 200 --path /login --path /` |
| production | `https://<production-host>` | same names as staging, different values | CI secret + hosting dashboard | owner only | `python3 <package>/tools/smoke.py --url https://<production-host> --expect-status 200 --path /login --path /` |

## Where values live

- **Local:** `.env` in the project root, gitignored. `.env.example` lists names only. DB and bucket names come from `.polier-slot`.
- **CI:** the provider's secret store; workflows reference names, never echo values.
- **Preview, staging, production:** hosting dashboard or platform secret store, one value per environment.
- Never in the repo, a brief, a screenshot, a log or a chat.

## Rules

- A variable name missing from this table, or missing at runtime, is a deployment failure: add it here and in the secret store, redeploy, then smoke again. Do not simply retry; fix the configuration first.
- `tools/smoke.py` is the post-deploy gate. Run it after every preview, staging and production deployment; it writes a gate record and exit 0 is required.
- Every environment has an `http(s)` smoke URL in the table. A row without one is an incomplete checklist and blocks release.
- Add or rename a variable in the same task as the code that uses it, for local, preview, staging and production.
- Local ports, database and bucket names come from `.polier-slot`; never hard-code them and never touch slot 0's data.
