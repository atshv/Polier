# Settings

**Settings** sits at the bottom of the sidebar. Project settings are committed in `dashboard.json`; machine settings stay on your computer.

## Project (committed)

| Section | Controls |
|---|---|
| **General** | project facts, your *"Me" handle* and the dashboard language (English or German, per browser) |
| **Features** | turn views on or off; hidden views leave the sidebar and the palette |
| **Labels** | id, title, colour and group of every label |
| **Templates** | task templates saved in `templates/tasks/` |

## This machine (runtime)

| Section | Controls |
|---|---|
| **Sessions** | provider command, permission mode, allowed tools, model, environment |
| **Gate commands** | the command behind each gate name, overriding `docs/quality.md` |
| **Guided setup** | open the setup, run it again |

The theme switch (☾) in the header and your density choice are stored in the browser.

## Guided setup

The **Guided setup** row opens the guided [first-run setup](polier:setup) at any time and runs it again. On a machine whose dashboard runtime did not exist yet, the first start opens it automatically once; an existing runtime without a setup record starts as `skipped`, so an upgrade never opens it by itself. The state is machine-local, in the runtime `config.json`; **Settings → Guided setup → Run it again** sets it back to `pending` so the page opens once more. Skipping it stops the automatic open without changing any project file.
