# Orchestration — <Project name>

> One page: how a task moves through this project, what the tools check, and
> where the records live. Copy it to `docs/orchestration.md`. The numbers live
> in `policy.json`, not in this file.

## Where the state lives

| File | Holds | Written by | Committed |
|---|---|---|---|
| `board.json` | plan: tasks, dependencies, scopes, status, stages | `tools/state.py` only | yes |
| `runs/<ID>.json` | execution: attempt counter, gate/review/state events | `tools/state.py`, gate events by `tools/gate.py` | yes |
| `reviews/approvals/AP-NNN.json` | human decisions: pending, granted, denied | `tools/approve.py` | yes |
| `policy.json` | limits, protected paths, approvals, denied commands | the owner | yes |
| `.polier-slot`, claims | liveness: ports per worktree, which session is on which task | `tools/slot.py`, `tools/claim.py` | no |

## The task loop

The lead runs the transitions; the worker runs the gates and reports, and the
reviewer writes the review.

```bash
python3 <package>/tools/dispatch.py                  # next wave, blocked tasks, conflicts
python3 <package>/tools/state.py set <ID> in_progress
# implement; run every gate from board.json with tools/gate.py
python3 <package>/tools/state.py set <ID> verifying
python3 <package>/tools/state.py set <ID> review
# reviewer writes reviews/<ID>.md
python3 <package>/tools/state.py set <ID> done --note "review pass, gates green"
```

`tools/state.py show <ID>` prints the board status against the run record,
gates, review, approvals and attempts; `check <ID> <status>` evaluates without
writing. A refused transition names the missing precondition and the command
that records it.

| To | Needs |
|---|---|
| `in_progress` | every dependency done; an attempt below the limit; fewer than `max_in_progress` tasks running; the stage not stopped or waiting |
| `verifying` | an open attempt in `runs/<ID>.json` |
| `review` | a passing record for every gate of the task |
| `done` | review `verdict: pass`; handoff when another task depends on this one; the run record; a granted `new_dependency` approval when a manifest is touched |
| `rework` | a note and a free review round |
| `blocked` | a note with the reason and what is needed |
| `failed` | a note |

**Attempts and rounds.** An attempt is one run of a task: it opens on
`in_progress`, closes as `pass`, `fail` or `cancelled`, capped by
`max_attempts_per_task`. A round is one review: `rework` adds one, capped by
`max_review_rounds`. Never reset a counter by editing a file. At a cap, stop and
escalate; `--force` needs a granted `state_override` approval and leaves a
warning in the record.

## Stages

A stage is complete when its blocking stages are complete, every task in it is
`done`, every `exit_gates` name has a passing record, and the owner decision is
`continue` or `stop`. While the decision is `pending`, the next stage's tasks
stay out of "Ready now". The decision goes on the board, not into chat.

## Approvals

The actions in `policy.json` → `approvals.actions` need a granted record in `reviews/approvals/` before they happen:

```bash
python3 <package>/tools/approve.py request --action new_dependency --task <ID> --note "adds <package> <version> for <purpose>"
python3 <package>/tools/approve.py list --status pending
python3 <package>/tools/approve.py grant AP-001 --note "ok"
```

`--action` is one of `new_dependency`, `scope_change`, `merge_to_base`,
`release`, `reopen_done`, `protected_path`, `state_override` — the list in
`policy.json`. A granted record is the approval; it does not expire. Deny writes
the same record with `status: denied`; do not ask again without new
information. A protected path is lead-only in the guard: an approval does not
let a worker write one.

## Escalation

Do not retry around a refusal and do not force without an approval.

1. Stop; do not edit `board.json`, `runs/` or `reviews/approvals/` by hand.
2. `python3 <package>/tools/state.py set <ID> blocked --note "<reason; what is needed>"`.
3. Ask the owner with two options and their consequences.
4. Resume as a new attempt after the decision.

Escalate at an exhausted attempt count, an exhausted round count, a scope
conflict between parallel tasks, a missing or denied approval, and a stopped
stage.

## Rules

- State changes only with `tools/state.py`; gates only with `tools/gate.py`;
  approvals only with `tools/approve.py`.
- `runs/`, `reviews/approvals/` and `board.json` are not edited by hand.
- Run `tools/dispatch.py` before starting a task; the first wave is the plan.
- `runs/` and `policy.json` belong to the project and are committed.
- `tools/audit.py` is the compliance view; `tools/check.py` is the project check.

## What is not covered

Approvals are cooperative evidence, not authentication: whoever can write the
file can forge a grant. Runs are text files and can be edited. Command matching
is static, and the tools are not a sandbox — a direct write bypasses every
checkpoint. The dispatch plan is a snapshot; re-run it.
