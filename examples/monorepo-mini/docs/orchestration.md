# Orchestration — canvas-mini

One page: how a task moves through this project, what the tools check, and where
the records live. The numbers are in `policy.json`, not in this file.

## Where the state lives

| File | Holds | Written by | Committed |
|---|---|---|---|
| `board.json` | plan: tasks, dependencies, scopes, status, stages | `tools/state.py` only | yes |
| `runs/<ID>.json` | execution: attempt counter, gate/review/state events | `tools/state.py`, gate events by `tools/gate.py` | yes |
| `reviews/approvals/AP-NNN.json` | human decisions: pending, granted, denied | `tools/approve.py` | yes |
| `policy.json` | limits (3 attempts, 3 tasks in progress, 3 review rounds), protected paths, approvals, denied commands | the owner | yes |
| `.polier-slot`, claims | liveness: ports per worktree, which session is on which task | `tools/slot.py`, `tools/claim.py` | no |

The `.generator/` folder is the Polier package copy; the commands below use it.

## The task loop

The lead runs the transitions; a worker runs the gates and reports; the reviewer
writes the review.

```bash
python3 .generator/tools/dispatch.py                  # next wave, blocked tasks, conflicts
python3 .generator/tools/state.py set <ID> in_progress
# implement; run every gate from board.json with tools/gate.py
python3 .generator/tools/state.py set <ID> verifying
python3 .generator/tools/state.py set <ID> review
# reviewer writes reviews/<ID>.md
python3 .generator/tools/state.py set <ID> done --note "review pass, gates green"
```

`state.py show <ID>` prints the board status against the run record, gates,
review, approvals and attempts. A refused transition names the missing
precondition and the command that records it.

| To | Needs |
|---|---|
| `in_progress` | an attempt below 3; fewer than 3 tasks in progress; the stage not stopped or waiting |
| `verifying` | an open attempt in `runs/<ID>.json` |
| `review` | a passing record for every gate of the task |
| `done` | review `verdict: pass`; handoff when another task depends on this one; the run record; a granted `new_dependency` approval when a manifest is touched |
| `rework` | a note and a free review round |
| `blocked` | a note with the reason and what is needed |
| `failed` | a note |

An attempt opens on `in_progress` and closes as `pass`, `fail` or `cancelled`.
A round is one review; `rework` adds one. At a cap, stop and escalate; `--force`
needs a granted `state_override` approval and leaves a warning in the record.

## Stages

A stage is complete when its blocking stages are complete, every task in it is
`done`, every `exit_gates` name has a passing record, and the owner decision is
not `pending`. `foundation` and `surface` are open; `engine-spike` and `web`
wait for their owner decision. The decision goes on the board, not into chat.

## Approvals

`AP-001` is a pending `new_dependency` request for `API-01` (httpx): the task
may not touch a `package.json` until the owner grants it.

```bash
python3 .generator/tools/approve.py request --action new_dependency --task API-01 --note "adds httpx <version> for <purpose>"
python3 .generator/tools/approve.py list --status pending
python3 .generator/tools/approve.py grant AP-001 --note "ok"
```

A protected path (`.env`, secrets, keys) is lead-only in the guard: an approval
does not let a worker write one. Denied commands (push, publish, deploy) never
run, whatever the role.

## Escalation

Do not retry around a refusal and do not force without an approval.

1. Stop; do not edit `board.json`, `runs/` or `reviews/approvals/` by hand.
2. `python3 .generator/tools/state.py set <ID> blocked --note "<reason; what is needed>"`.
3. Ask the owner with two options and their consequences.
4. Resume as a new attempt after the decision.

Escalate at an exhausted attempt count, an exhausted round count, a scope
conflict between parallel tasks, a missing or denied approval, and a stopped
stage.

## What is not covered

The tools enforce the static rules they can see: board transitions, recorded
gates, attempts, rounds, approvals and the write/command guard. A process that
edits `runs/`, `board.json` or an approval file with the shell is outside the
guard; `tools/audit.py` reports the contradiction, it cannot prove what
happened.
