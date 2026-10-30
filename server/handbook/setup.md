# First-run setup

On a machine that has not run the dashboard before, a fresh start opens a short guided setup instead of the board, so a new project is connected before you work in it.

## When it appears

The setup state is machine-local, in the dashboard runtime `config.json`. It is `pending` on a machine whose runtime config did not exist yet, and after **Run it again** resets it. While it is `pending` a fresh start opens `#/setup` instead of `#/board`.

- An existing dashboard runtime without a setup record reads as `skipped`: an upgrade never opens the wizard by itself, but it stays reachable from **Setup** and **Settings**.
- The page is a guided, skippable sequence, not a form you must finish.
- Once you finish or skip, the dashboard never opens setup on its own again — but you can reopen it at any time.

## The steps

| Step | What it does |
|---|---|
| Welcome | introduces the sequence and its **Skip setup** button |
| GitHub | connects the `gh` CLI through the existing device flow (see [GitHub integration](polier:github-integration)); left out when `dashboard.json` → `features.github` is off (the stepper then has five steps) |
| AI provider | picks Claude Code (default, command `claude`) or a custom command; a custom command that is not on the PATH is flagged **not found on PATH** here and in the summary, and the step is not marked done |
| Sign in | probes `claude auth status` and shows whether the CLI is installed and signed in, with the copyable `claude auth login` command and **Check again** |
| Model | optional `--model` override — `opus`, `sonnet`, `haiku` or the provider default; Claude Code only, so a custom command runs as configured without an extra `--model` and the field is disabled |
| Done | a summary of what was connected, then **Open the board** (or the plan editor when there is no board yet) |

The sign-in probe is read-only and only runs for Claude Code; a custom provider shows no probe. A signed-out CLI reads as not signed in and shows the copyable command; the state is unknown only when the check cannot run. The provider and model choices go through `PUT /api/config` → `session`, not through the project.

## Skip it

**Skip setup** is shown on every step of a writable dashboard while the state is `pending`. It leaves the wizard and opens the board — or the plan editor when there is no board yet. On a read-only dashboard the button is disabled; if `GET /api/setup` fails, the page offers **Try again** and **Open the board** / **Open the plan editor** instead.

## Reopen it

- **Setup** in the sidebar's system group.
- **Open guided setup** in the command palette (Ctrl/Cmd+K).
- **Settings → Guided setup → Run it again**, which sets the state back to `pending` so the page opens once more.

## Where the state lives

Everything is machine-local and never committed: the setup state (`pending`, `done` or `skipped`, plus when it last changed) and the provider/model choices live in the dashboard runtime `config.json`, next to the session settings and gate-command overrides. The page only connects tools; it creates no project file.

## Turn it off

`dashboard.json` → `features.setup` (default `true`). Set it to `false` to hide the view and the auto-open.

## Read-only dashboard

A read-only dashboard (`--read-only` or `--role viewer`) does not auto-open the wizard; it stays reachable from **Setup**. The page shows the setup and runs the probe, but saving the provider or model and finishing or skipping are disabled; the API answers `403` for them. The Done step's **Open the board** still leaves the wizard without saving anything, and the error fallback offers the same way out.

## From the API

`GET /api/setup` returns the state, the chosen provider and the available providers; `POST /api/setup` records `complete`, `skip` or `reset`. See [Settings and views](polier:api-settings) for the fields.
