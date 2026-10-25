# Gate Catalogue: PostgreSQL

> Copy the gates the project has to `docs/gates/postgres.md`; delete the rest. Replace every `<...>`; the database name always comes from `.polier-slot` (`<project>_slot_N`), never from a hard-coded string.

| Gate | Command shape | Expected |
| --- | --- | --- |
| `db-migrate` | `psql "$DATABASE_URL" -f <migration>.sql` or the project's migrate command [VERIFY: from manifest/docs] | exit 0, migrations applied |
| `db-seed` | `psql "$DATABASE_URL" -f <seed>.sql` [VERIFY: from manifest/docs] | exit 0, seed rows present |
| `db-test` | the project's integration test command against the slot database [VERIFY: from manifest/docs] | exit 0, tests pass |
| `db-reset` | drop and recreate the slot database, then migrate [VERIFY: from docs] | exit 0, empty schema rebuilt |

- `DATABASE_URL` (or the project's variable name) comes from `.polier-slot` or the environment; never print it or commit it.
- `db-reset` is destructive: mark tasks with `"exclusive": ["db"]` and run it only against your slot's database.

## Pitfalls

- A shared database makes tests order-dependent: one database per slot, reset before the suite.
- Never edit an applied migration; add a new one.
- Ports come from the slot formula, not 5432: read `.polier-slot` before starting a server.
- Lock waits and leftover connections look like hangs; close connections in fixtures and set a timeout.
- Never touch slot 0's data and never run a destructive command against production.
- A migration that fails halfway leaves the slot database dirty: rerun `db-reset`, then migrate.
