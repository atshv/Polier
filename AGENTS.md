# Working on Polier

Polier is a DeepSeek Harness plugin and a Claude Code plugin plus the Python rules and tools they call. This file is for agents and people changing Polier itself; projects built with Polier get their own `AGENTS.md` from `templates/AGENTS.template.md`.

## Layout

| Path | What |
|---|---|
| `plugin/` | the DSH plugin (ESM, no build step): `index.mjs` wiring, `lib/` context, guard, tools, sessions; `test/` with `harness.mjs` |
| `claude/` | the Claude Code adapter over `plugin/lib/`: `server.mjs` (MCP, elicitation), `hook.mjs`, `hooks.json`, `statusline.mjs`, `lib/host.mjs`; `agents/` (generated); `test/` |
| `.claude-plugin/` | `plugin.json` and `marketplace.json` (generated), `icon.png` |
| `core/` | the rules, Python standard library only; `core/tests/` |
| `tools/` | one CLI per rule set; the plugin calls these, never re-implements them |
| `factory/` | `catalog.json` (source) and `CATALOG.md` (generated) |
| `roles/` | `roles.json` and one instruction file per specialist role |
| `prompt/`, `templates/`, `guide/` | the process, the rubric, document templates, the owner's cheatsheet |
| `tests/` | tool tests; `tests/fixtures/` holds the S and L reference projects |
| `scripts/` | repository scripts: `check.py`, `tools-doc.mjs`, `roles-doc.py`, `claude-plugin.py`, `release.py` |
| `docs/` | `architecture.md`, `tools.md` and `roles.md` (generated), `guard-limits.md` |

## Commands

- All tests: `npm install && npm test`
- Plugins only: `node --test plugin/test/*.test.mjs claude/test/*.test.mjs`
- Python only: `python3 -m unittest discover -s tests && python3 -m unittest discover -s core/tests -t .`
- Checks: `npm run check` — generated pages and plugin files current, pyflakes silent, no unused export in `plugin/lib` or `claude/lib`, every module parses (needs `pip install pyflakes`)
- Claude Code: `claude plugin validate .` checks the manifest; `claude --plugin-dir .` runs a session with this checkout
- Generated pages: `npm run docs` after changing a tool definition, the guide, `roles/`, `factory/catalog.json` or `VERSION` (it also writes `.claude-plugin/` and `claude/agents/`)

## Rules

- No runtime dependency: Python stdlib, Node built-ins, harness services looked up at call time. A missing optional service degrades, it never breaks the boot.
- One implementation per rule, in `core/`. The plugin forwards writes and commands to `tools/guard.py` and never re-implements a rule; `plugin/lib/` only reads files for the live context. `claude/` adapts `plugin/lib/` to Claude Code and holds no tool or rule of its own.
- Human decisions go through `ctx.approval` (an approval prompt; in Claude Code an MCP elicitation dialog), never through chat text or a new slash command. Records are written by `tools/*.py` only.
- The live context must stay short and must be empty outside a Polier project.
- Store and legal facts in the catalog or templates carry `[VERIFY: …]` unless a dated source backs them.
- No dead code: a function only a test uses, a helper of a removed feature or an unused export goes.
- Nothing private or project-specific in templates, fixtures or tests.
- Tool results say what happened and what comes next (`next`, `remaining`); reports to the human separate what was observed, what was inferred and what was not checked.
- Tests use the real harness packages and the fixtures in `tests/fixtures/`, not module mocks. Do not freeze arbitrary caps or call orders in tests.

## Commits and releases

Commit subjects follow Conventional Commits: `feat:`, `fix:`, `perf:`, `docs:`, `test:`, `ci:`, `chore:`, `refactor:`, with an optional scope (`feat(plugin): …`). A breaking change gets `!` (`feat!: …`) or a `BREAKING CHANGE:` footer. On every push to `main`, `scripts/release.py` reads the commits since the tag of `VERSION`. Before 1.0 every version is a pre-release: `feat`, `fix` and `perf` bump the third number, a breaking change the second. From 1.0 on: `feat` → minor, `fix`/`perf` → patch, breaking → major. It writes `VERSION`, `package.json` and a `CHANGELOG.md` section, and the release workflow tags `vX.Y.Z` and publishes the notes (as a pre-release below 1.0). 1.0 is set by hand when Polier is ready to be released. For a release with hand-written notes, bump `VERSION` and add the `## X.Y.Z` section yourself in the same push. Never move or reuse a tag.
