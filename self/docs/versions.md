# Versions: Polier next

> Every dependency the Polier repository and the new features need. Polier has no runtime dependency; everything below is a runtime prerequisite or a development tool.

| Tool / library | Exact version | Source URL | Date checked | Approved by |
| --- | --- | --- | --- | --- |
| Python | ≥ 3.9 (CI: 3.12; local: 3.13.18) | `core/preflight.py` `MIN_PYTHON`; `.github/workflows/test.yml` | 2026-11-12 | lead |
| Node.js | ≥ 20 (CI: 22; local: 22.23.4) | `package.json` `engines`; `.github/workflows/test.yml` | 2026-11-12 | lead |
| git | ≥ 2.31 for evals (local: 2.43.0) | https://code.claude.com/docs/en/plugin-evals.md#requirements | 2026-11-12 | lead |
| Claude Code | ≥ 2.1.269 for `claude plugin eval` (local: 2.1.323) | https://code.claude.com/docs/en/plugin-evals.md#requirements | 2026-11-12 | lead |
| `@deepseek-ai/cordis` (dev) | 4.1.0 | `package.json` | 2026-11-12 | lead |
| `@deepseek-ai/dsh-skill` (dev) | 0.2.2-rc.1 | `package.json` | 2026-11-12 | lead |
| `@deepseek-ai/dsh-system-prompt` (dev) | 0.2.2-rc.1 | `package.json` | 2026-11-12 | lead |
| `@deepseek-ai/dsh-tool-executor-native` (dev) | 0.2.2-rc.1 | `package.json` | 2026-11-12 | lead |
| `@deepseek-ai/dsh-tools` (dev) | 0.2.2-rc.1 | `package.json` | 2026-11-12 | lead |
| pyflakes (dev, CI) | unpinned [VERIFY: pin in the workflow before release] | `.github/workflows/test.yml` | 2026-11-12 | lead |
| Eval agent model | pinned per run with `--model` [VERIFY: model ID when the eval workflow is written] | ADR-0001 | 2026-11-12 | owner |

## Rules

1. No new runtime dependency (`AGENTS.md`). The features of the first stage add none.
2. A version change updates the manifest, the workflow and this table in the same task.
