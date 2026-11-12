# ADR-0001: Process evals with `claude plugin eval` against the real plugin

**Date:** 2026-11-12 · **Status:** proposed · **Supersedes:** –

## Context

F1 must show whether an agent with Polier follows the process better than without it (US1, D1). Claude Code ≥ 2.1.269 has `claude plugin eval`: each case runs as a fresh `claude -p` session with only the plugin loaded, three runs per arm, optionally against a no-plugin baseline (`docs/research/claude-plugin-eval.md`, read from https://code.claude.com/docs/en/plugin-evals.md on 2026-11-12). Facts that shape the decision:

- Runs are non-interactive: MCP elicitation cannot be answered, so every owner dialog fails closed. That is the behaviour to test, not a gap.
- Hooks load with the plugin. The plugin's real MCP server starts only with `--mocks off` or `--allow-real-servers`, and its tools need `--allow-tools "mcp__plugin_polier_polier__*"`.
- `Write`, `Edit` and `Bash` need explicit grants; granted Bash runs in the OS sandbox (bubblewrap and socat on Linux).
- The workspace starts empty; `context.scaffold_script` with `--scaffold` builds a fixture project and its git repository.
- Graders: `regex`, `tool_used`, `tool_order`, `file_exists` cost nothing; `llm` calls a judge. There are no custom-code graders.
- Model calls use the maintainer's credentials and are billed.

## Decision

We run 10–20 process cases from `evals/` with `claude plugin eval . --mocks off --allow-tools "mcp__plugin_polier_polier__*" Write Edit --scaffold --ablation with-without`, decide each case on outcome graders scored in both arms and keep Polier-tool graders as `arm: with-only` indicators, on manual dispatch and before releases, with a pinned model and `--max-cost-usd`.

## Consequences

- **Positive:** measures the real plugin (server, hooks, agents); the delta is fair because the baseline can pass every scored grader; free graders keep runs cheap and stable.
- **Negative:** each run costs money and needs the API key in CI; scores are advisory because hooks and the real server run outside the sandbox (run CI in a fresh runner); no Bash in cases unless the runner has a sandbox backend.
- **Binds:** `evals/`, `package.json` (`evals` script), `.github/workflows/evals.yml`, `.gitignore` (`evals/results/`).
- **Prevents:** process regressions shipped unnoticed; a delta inflated by graders the baseline cannot pass.

## Case shape

Each case seeds a small project (`fixture.sh`: `board.json`, `factory.json`, `policy.json` and files, `git init`), sends a plain owner sentence, and grades the outcome. First cases: close a station while an item is open; close a complete station (dialog fails closed, `factory.json` unchanged); a worker asked to edit outside its scope; "yes" in the chat for a new dependency; record a gate; mark an item done with evidence; delegate a task to its role; a reviewer asked to fix code.

## AI integration (ARC-16)

- **Provider and model:** Anthropic through Claude Code; agent model pinned with `--model`, judge with `--judge-model` (IDs fixed in the eval task, `docs/versions.md`).
- **Where prompts live:** `evals/<case>/prompt.md`; graders in `evals/<case>/graders/`.
- **Cost limit:** `--max-cost-usd` per run in the workflow; locally the maintainer's own limit. No per-user cost: Polier has no users of a service.
- **Fallback:** without a key or with a hit ceiling the run is partial (exit 2) and is not a pass; tests and checks still gate every push.
- **Keys:** only in the GitHub secret or the maintainer's login (`docs/environments.md`).

## Third-party services (ARC-10)

| Service | Use | Terms | Region | Cost |
| --- | --- | --- | --- | --- |
| Anthropic API via Claude Code | eval runs and judge | Anthropic commercial or consumer terms of the maintainer's account [VERIFY: which terms apply to the account used in CI] | provider default | per token, capped per run |
| GitHub Actions | CI for tests and evals | GitHub terms | GitHub hosted | free tier for public repositories `[UNVERIFIED]` |

## Alternatives

- **Hand-written harness around `claude -p`** — rejected: re-implements isolation, baseline and grading that `claude plugin eval` already has.
- **Mocked Polier MCP server** — rejected: tests the mock, not Polier's guard and records.
- **LLM judge on the whole transcript** — rejected as the main signal: unstable on long text; kept only for short final messages.
