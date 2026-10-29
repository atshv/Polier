# Core concepts

A short tour of the words the dashboard uses. Each one maps to a file you can open.

## Board

`board.json` holds the stages and tasks. A task has an ID, a goal, a write scope (`scope.write`), acceptance criteria, gates, dependencies and a status. The board is only changed by `tools/state.py` (status) and the validated plan editor (everything else).

## Stages

Stages group tasks into milestones with **exit gates** and an **owner decision** (`continue`, `stop` or `pending`). The next stage only opens when the previous one is complete and you decided to continue. The **Cycles** view shows each stage with its burndown.

## Statuses

| Status | Meaning | Next |
|---|---|---|
| `pending` | planned, not started | `claimed`, `in_progress` |
| `claimed` | a session holds the task | `in_progress` |
| `in_progress` | an agent is working | `verifying` |
| `verifying` | gates are being checked | `review`, `rework` |
| `review` | waiting for a verdict | `done`, `rework` |
| `rework` | review or gates failed | `in_progress` |
| `blocked` | waits on something outside the task | `pending`, `in_progress` |
| `failed` | attempts exhausted | `pending`, `in_progress` |
| `done` | proven and reviewed | `rework` |

`rework`, `blocked` and `failed` need a note that says why.

## Gates and evidence

A gate is a named check (`unit`, `lint`, `e2e`, …) with a command. Running it through `tools/gate.py` or the dashboard writes a record with the exit code, duration and a checksum of the log to `runs/<ID>.json` and `reviews/evidence/`. "Tests pass" in a chat does not count; only records do.

## Claims

A claim says which session works on a task right now. It prevents two agents from editing the same files. Claims live outside the repository in the shared git folder and are released when the session ends.

## Approvals

Some actions need the owner: a new dependency, a scope change, a merge to the base branch, a release, reopening a done task, a protected path. An agent requests an approval, you grant or deny it with a note. Pending approvals appear in **Approvals**, in the inbox and in the dispatch plan.

## Write guard and policy

`policy.json` sets the limits: attempts per task, parallel tasks, review rounds, protected paths and denied commands (`git push`, `npm publish`, …). The guard checks every write of an agent against the task scope and the policy.
