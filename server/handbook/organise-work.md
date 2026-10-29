# Organise work with labels, filters and views

Find the right tasks quickly and act on many at once.

## Labels

Labels group work across stages: type (`bug`, `feature`), risk, origin or anything you need. Define them once in **Settings → Labels** (id, title, colour, group); they are stored in the committed `dashboard.json`.

Assign labels in the task drawer under **Properties**, in the Plan editor, in bulk, or from the CLI:

```bash
python3 tools/settings.py label add risk-high "Risk: high" --color red --group risk
python3 tools/plan.py update ENG-02 --labels feature,risk-high
```

Labels never change a task's write scope.

## Filters

On **Board** and **Table**, **+ Filter** adds a condition: a field, an operator and a value.

| Field kind | Operators |
|---|---|
| text — ID, title, stage, package, owner, review verdict | is, is not, contains, does not contain, empty |
| status | is, is not, any of, none of |
| label | any of, none of, empty |
| number — complexity, estimate, tokens, attempt, missing gates | =, ≠, >, ≥, <, ≤, empty |
| yes/no — ready, running, claimed, blocked | is |
| budget | is (ok, warn, over) |

All conditions must match. The header search (**/**) filters by ID and title on top.

## Saved views

When the filters, grouping or sort differ from the default, **Save view** stores them as a committed `views/<id>.json`, shared with everyone on the project. Built-in views — *Ready now*, *Blocked*, *Review queue*, *Over budget*, *No estimate*, *Mine* — are always there.

## Bulk actions

1. Click **Select** on Board or Table.
2. Tick tasks, click cards, or **Select all**.
3. Choose an action in the bar: move to a status (with a note where required), claim or release, replace labels, set an estimate.
4. **Done** or Esc leaves selection mode.

Every task is checked on its own; refused transitions are listed per task instead of failing the whole batch.

## Your Work and the inbox

**Your Work** is your queue: the inbox first, then your tasks, reviews, approvals, blocked tasks, budget warnings and running sessions. Set your handle in **Settings → General → "Me" handle** so the dashboard knows which tasks are yours. Read marks are local to your machine.
