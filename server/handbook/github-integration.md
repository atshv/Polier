# GitHub integration

Connect your GitHub account once and Polier shows the pull requests and CI runs of the project, maps them to tasks, and agent sessions can use `gh` and the GitHub MCP connector.

## Connect your account

**Integrations → GitHub → Connect GitHub** (also under **Settings → Integrations**):

1. Polier asks GitHub for a one-time code and shows it with a **Copy** button.
2. Open **github.com/login/device**, sign in and enter the code.
3. The dialog switches to *Connected as …* on its own.

Prefer a token? Open **Use a personal access token instead** and paste a classic token with the scopes `repo` and `read:org`.

> [!NOTE]
> Polier stores no GitHub credential. The sign-in runs through the GitHub CLI (`gh auth login`), which keeps the token in its own store — the same one your terminal uses. **Disconnect** signs `gh` out on this machine.

## Requirements

| Needed | Why |
|---|---|
| The GitHub CLI (`gh`) | Polier talks to GitHub only through it |
| A GitHub `origin` remote | to know which repository to read |
| Scopes `repo`, `read:org` | to read private repositories and organisation checks |

## What you get

- **Pull requests** with draft state and the combined check result.
- **Workflow runs** with status and conclusion.
- **Task mapping**: a branch `task/<ID>` (or the task's `branch` field) links a PR and its CI to the task.
- **Agents**: sessions inherit the `gh` login; add the GitHub [connector](polier:mcp-connectors) to give them GitHub tools.

Results are cached for 30 seconds; **Refresh** asks again.

## From the command line

```bash
gh auth login --web
python3 tools/github.py status
```
