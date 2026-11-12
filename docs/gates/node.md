# Gates: Node and Claude Code (plugin/, claude/, evals/)

> Verified on 2026-11-12 with Node 22.23.4 and Claude Code 2.1.323. Run each with `pl_gate`.

| Gate | Command | Expected |
| --- | --- | --- |
| `tests` | `npm test` | `# fail 0` for `plugin/test` and `claude/test`, Python suites `OK` |
| `check` | `npm run check` | `OK: generated pages current, no dead code found, modules parse` |
| `validate` | `claude plugin validate . --strict` | `Validation passed` |
| `evals-smoke` | `claude plugin eval . --case close-open-station --runs 1 --ablation none --mocks off --allow-tools "mcp__plugin_polier_polier__*" Write Edit --scaffold --trust-plugin --no-publish --max-cost-usd 2` | exit 0; the case scores 1.0 |

## Rules

- No build step and no runtime dependency; `node --check` runs inside `check`.
- After changing a tool definition, the guide, `roles/`, the catalog or `VERSION`: `npm run docs`, then `check`.
- `evals-smoke` calls the model with the maintainer's credentials and costs money (capped at 2 USD); it runs only in tasks that change `evals/` or the plugin's behaviour in a case. A run that exits 2 (ceiling hit) is not a pass.
- Plugin tests start the real server and hook processes on throwaway git projects; no module mocks (`AGENTS.md`).
