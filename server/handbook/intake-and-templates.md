# Intake and task templates

New ideas should not jump straight onto the board. Intake collects them; you decide what becomes a task. Templates make recurring task shapes quick to create.

## Add a proposal

**Intake → New proposal**, or from the CLI:

```bash
python3 tools/intake.py add --title "Dark mode for the web app" --kind request --priority medium
```

A proposal has a kind (`idea`, `issue`, `request`, `question`), a priority, a source and optional links. It is committed as `intake/IN-001.json`.

## Triage

| Decision | Result |
|---|---|
| **Accept** | creates a validated `pending` task in the stage you choose and links it back |
| **Reject** | closes the proposal with a reason |

Accepting can apply a template, so the new task arrives with scope, gates and labels already filled in.

## Task templates

A template is a committed `templates/tasks/<id>.json` with the reusable part of a task: scope, acceptance, gates, complexity, labels, estimate.

- Save one from an existing task: drawer → **Save as template**, or `python3 tools/templates.py save --from-task ENG-01 --id cpp-module`.
- Use it in the Plan editor, when accepting intake, or via the API (`template` field).

Templates never bypass validation; the resulting task is checked like any other.
