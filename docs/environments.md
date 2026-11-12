# Environments: Polier next

> Polier is a CLI and two harness plugins: nothing is deployed and there is no URL to smoke. The environments are where its checks run. Variable names only — never values.

## Checklist

| Environment | Runs | Required variables (names only) | Set in | Who may change | Smoke check |
| --- | --- | --- | --- | --- | --- |
| local | `npm test`, `npm run check`, `npm run evals` | `ANTHROPIC_API_KEY` or the maintainer's Claude Code login, for evals only | the maintainer's shell or Claude Code login; never a file in the repo | maintainer | `python3 tools/preflight.py .` |
| CI test (`test.yml`) | tests, checks, fixture checks on every push and PR | none | — | maintainer | the workflow's own steps |
| CI evals (`evals.yml`, new) | `npm run evals` on manual dispatch and before a release | `ANTHROPIC_API_KEY` | GitHub Actions repository secret | owner only | exit code of `claude plugin eval` |
| CI release (`release.yml`) | version, tag, notes on push to `main` | `GITHUB_TOKEN` (provided by Actions) | GitHub | — | the workflow's own steps |

## Where values live

- **Local:** the maintainer's environment or Claude Code login. Never in `.env` files of the repository.
- **CI:** GitHub Actions secrets; workflows reference names and never echo values. The eval workflow runs only on manual dispatch and from `main`, so a pull request from a fork cannot reach the key.
- Never in the repo, a brief, an eval case, a result file or a chat.

## Rules

- The eval workflow sets `--max-cost-usd` (ADR-0001); a run that hits it exits 2 and is not a pass.
- Eval results (`evals/results/`) are gitignored; a release note quotes the score, not the transcripts.
