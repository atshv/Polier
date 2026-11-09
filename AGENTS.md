# Working on Polier

Polier is a DeepSeek Harness plugin plus the Python rules and tools it calls. This file is for agents and people changing Polier itself; projects built with Polier get their own `AGENTS.md` from `templates/AGENTS.template.md`.

## Layout

| Path | What |
|---|---|
| `plugin/` | the DSH plugin (ESM, no build step): `index.mjs` wiring, `lib/` context, guard, tools, sessions; `test/` with `harness.mjs` |
| `core/` | the rules, Python standard library only; `core/tests/` |
| `tools/` | one CLI per rule set; the plugin calls these, never re-implements them |
| `factory/` | `catalog.json` (source) and `CATALOG.md` (generated) |
| `prompt/`, `templates/`, `guide/` | the process, the rubric, document templates, the owner's cheatsheet |
| `tests/` | tool tests; `tests/fixtures/` holds the S and L reference projects |

## Commands

- All tests: `npm install && npm test`
- Plugin only: `node --test plugin/test/*.test.mjs`
- Python only: `python3 -m unittest discover -s tests && python3 -m unittest discover -s core/tests -t .`
- Catalog page: `python3 tools/factory.py catalog --write` after every change to `factory/catalog.json`
- Lint: `python3 -m pyflakes core tools tests` must be silent (outside `tests/fixtures/`)

## Rules

- No runtime dependency: Python stdlib, Node built-ins, harness services looked up at call time. A missing optional service degrades, it never breaks the boot.
- One implementation per rule. The write and policy rules exist in Python and JS; `core/tests/write_cases.json` and `policy_cases.json` are the shared tables both test suites run. Change both sides together.
- Human decisions go through `ctx.approval` (an approval prompt), never through chat text or a new slash command. Records are written by `tools/*.py` only.
- The live context must stay short and must be empty outside a Polier project.
- Store and legal facts in the catalog or templates carry `[VERIFY: …]` unless a dated source backs them.
- No dead code: a function only a test uses, a helper of a removed feature or an unused export goes.
- Nothing private or project-specific in examples, templates or tests.

## Releasing

Bump `VERSION`, add a `## X.Y.Z` section at the top of `CHANGELOG.md` with what a running project must do, push to `main`. The release workflow syncs `package.json`, runs the tests, tags `vX.Y.Z` and publishes the notes.
