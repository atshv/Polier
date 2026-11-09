# Runbook: <Project name>

> Station 9 (operate). Copy to `docs/runbook.md`. Who watches what, and what to do when it breaks. Names of people and tools, never secrets.

## Monitoring

| Signal | Tool | Alert goes to | Threshold |
| --- | --- | --- | --- |
| Errors/crashes | `<Sentry, Crashlytics>` | `<owner>` | `<new issue>` |
| Uptime | `<UptimeRobot, Better Stack>` | `<owner>` | `<2 failed checks>` |
| Costs | `<provider budget alert>` | `<owner>` | `<CHF …/month>` |

## Logging

- Where logs live, retention `<14 days>`; no secrets or personal data in logs.

## Backups

- Schedule `<daily>`, location `<…>`, last restore drill `<YYYY-MM-DD>`, restore command `<…>`.

## Incidents

1. Check the status page/monitor; confirm the outage.
2. Roll back with `docs/releasing.md#rollback` if the last release caused it.
3. Tell users through `<status page, in-app banner, email>`.
4. Write a short postmortem in `docs/adr/` or `docs/incidents/`.

## Support

- Channel: `<email/form>` linked in `<app, store listing>`; answer within `<2 working days>`.
- Data requests (access, deletion) within `<30 days>`.

## Feedback

- Feedback and bug reports become board tasks through the lead: `<how>`.

## Updates

- Dependencies: `<Dependabot/Renovate weekly>`; security fixes within `<7 days>`.
- Stores: OS/SDK update every year before the store deadline; review policy changes `<quarterly>`.
