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
| `scripts/` | repository scripts: `check.py`, `tools-doc.mjs`, `release.py` |
| `docs/` | `architecture.md`, `tools.md` (generated), `guard-limits.md` |

## Commands

- All tests: `npm install && npm test`
- Plugin only: `node --test plugin/test/*.test.mjs`
- Python only: `python3 -m unittest discover -s tests && python3 -m unittest discover -s core/tests -t .`
- Checks: `npm run check` — generated pages current, pyflakes silent, no unused export in `plugin/lib`, every module parses (needs `pip install pyflakes`)
- Generated pages: `npm run docs` after changing a tool definition, the guide or `factory/catalog.json`

## Rules

- No runtime dependency: Python stdlib, Node built-ins, harness services looked up at call time. A missing optional service degrades, it never breaks the boot.
- One implementation per rule. The write and policy rules exist in Python and JS; `core/tests/write_cases.json` and `policy_cases.json` are the shared tables both test suites run. Change both sides together.
- Human decisions go through `ctx.approval` (an approval prompt), never through chat text or a new slash command. Records are written by `tools/*.py` only.
- The live context must stay short and must be empty outside a Polier project.
- Store and legal facts in the catalog or templates carry `[VERIFY: …]` unless a dated source backs them.
- No dead code: a function only a test uses, a helper of a removed feature or an unused export goes.
- Nothing private or project-specific in templates, fixtures or tests.
- Tool results say what happened and what comes next (`next`, `remaining`); reports to the human separate what was observed, what was inferred and what was not checked.
- Tests use the real harness packages and the fixtures in `tests/fixtures/`, not module mocks. Do not freeze arbitrary caps or call orders in tests.

## Commits and releases

Commit subjects follow Conventional Commits: `feat:`, `fix:`, `perf:`, `docs:`, `test:`, `ci:`, `chore:`, `refactor:`, with an optional scope (`feat(plugin): …`). A breaking change gets `!` (`feat!: …`) or a `BREAKING CHANGE:` footer. On every push to `main`, `scripts/release.py` reads the commits since the last tag — `feat` → minor, `fix`/`perf` → patch, breaking → major — writes `VERSION`, `package.json` and a `CHANGELOG.md` section, and the release workflow tags `vX.Y.Z` and publishes the notes. For a release with hand-written notes, bump `VERSION` and add the `## X.Y.Z` section yourself in the same push. Never move or reuse a tag.
