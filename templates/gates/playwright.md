# Gate Catalogue: Playwright (e2e)

> Copy the gates the project has to `docs/gates/playwright.md`; delete the rest. Replace every `<...>`; take the config and browser versions from the manifest.

| Gate | Command shape | Expected |
| --- | --- | --- |
| `e2e` | `npx playwright test` [VERIFY: from manifest/docs] | exit 0, "N passed" |
| `e2e-one` | `npx playwright test <spec> --project=<name>` [VERIFY: project names from config] | exit 0, the spec passes |
| `e2e-report` | `npx playwright show-report` (local only) [VERIFY: from docs] | opens the HTML report |

- Browsers: `npx playwright install --with-deps <browser>` [VERIFY: browsers and CI setup from docs].
- `e2e` is concurrent-hostile: mark tasks `"exclusive": ["e2e"]`; wait for the lock, never run a second instance against the same port.
- The app under test starts on the slot's ports from `.polier-slot`; the config reads them from environment variables.

## Pitfalls

- Port collisions are the most common failure: read `.polier-slot`, never hard-code 3000/3101.
- Headless browser dependencies and fonts differ on Linux CI; install them with the browser step, not in the test.
- The browser cache (`~/.cache/ms-playwright`) is not in the repo and is slow on a cold CI; use the project's cache rule [VERIFY: from CI config].
- `test-results/` and `playwright-report/` are artifacts, never committed.
- Flaky tests are a defect: fix the wait or the fixture, never add retries to make a gate pass.
- Another session may run e2e; never kill its server or browser with `pkill`.
