# Gates: Python (core/, tools/, tests/)

> Polier's own commands, verified on 2026-11-12 in this repository (Python 3.13.18, CI 3.12). Run each with `pl_gate`; the record under `reviews/evidence/` is the evidence.

| Gate | Command | Expected |
| --- | --- | --- |
| `tests` | `npm test` | Node suites `# fail 0`; both Python suites end with `OK` |
| `check` | `npm run check` | `OK: generated pages current, no dead code found, modules parse` (needs `pip install pyflakes`) |
| `fixtures` | `python3 tools/check.py tests/fixtures/minimal-cli && python3 tools/check.py tests/fixtures/monorepo-mini && python3 tools/audit.py --root tests/fixtures/monorepo-mini` | two `passes the mandatory checks` lines and `audit: 0 error(s)` |
| `line` | `python3 tools/check.py .` | `OK: … passes the mandatory checks.` for this project |
| `audit` | `python3 tools/audit.py --root .` | `audit: 0 error(s)` |

## Rules

- Python standard library only; a new import outside it is a new dependency and is refused.
- Single test while working: `python3 -m unittest discover -s tests -p 'test_<name>.py'` or `python3 -m unittest core.tests.test_<name>`; the gate is always the full `npm test`.
- Never change an existing test to make it pass; a changed assertion needs the reason in the review.
