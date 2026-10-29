# Orchestration — Keeping a Running Project on the Plan

`board.json` says what should happen; it cannot say what is happening. A running
project also needs a record of attempts, a place for human decisions and rules
that do not drift. Those live in separate files, and every write goes through a
tool that checks the preconditions. Applies when the project has a
`policy.json`; without it the project is not broken, but the policy checkpoints
degrade: the transition table, the note rules and the `reopen_done`/
`state_override` approvals still apply, the gate/review/attempt/concurrency
checks become warnings, and the dependency approval is not checked. Generated
projects get a shorter copy of this model as `docs/orchestration.md`.

## The five stores

| Store | Holds | Written by | Committed |
|---|---|---|---|
| `board.json` | plan state: tasks, dependencies, scopes, status, stage decisions | `tools/state.py`, for the lead | yes |
| `runs/<ID>.json` | execution state: attempt counter, gate/review/state events, last result | `tools/state.py`; gate events by `tools/gate.py` | yes |
| `reviews/approvals/AP-NNN.json` | human decisions: pending, granted, denied | `tools/approve.py` | yes |
| `policy.json` | rules: limits, protected paths, required approvals, denied commands | the generator, later the owner | yes |
| `polier/claims/<ID>.json` (git common dir) | liveness: which session is on which task, last heartbeat | `tools/claim.py` and the harness | no |

The board says a task is `review`; the run record says this is attempt 2 of 3
and which gates passed when. A claim says a session is on the task now; it
never changes the board.

## The task loop

The lead owns the transitions; the worker runs the gates and reports, the
reviewer writes the review. `tools/state.py` is the only writer.

1. Run `tools/dispatch.py`; take the first wave.
2. Claim the task, take its worktree when the board requires one.
3. `set <ID> in_progress` opens an attempt (N of M), sets the run state to
   `running`, appends a `start` event.
4. The worker implements and runs every gate with `tools/gate.py`; each run
   appends a `gate` event.
5. `set verifying` needs an open attempt; `set review` a passing record for
   every gate in the task.
6. The reviewer writes `reviews/<ID>.md`; `set done` needs its `verdict: pass`,
   the handoff when other tasks depend on it, the run record, and a granted
   `new_dependency` approval when a manifest is touched. `set rework --note`
   closes the attempt as `fail` and starts a round.
7. A `done` task is reopened only with a granted `reopen_done` approval.

## Checkpoints

`tools/state.py` evaluates each transition, refuses with the missing
precondition and names the command that fixes it; `check <ID> <status>`
evaluates without writing.

| To | Preconditions (hard unless noted) |
|---|---|
| `in_progress` | every `depends_on` task done; tokens used < `budget.max_tokens_per_task` (when set); attempts opened < `max_attempts_per_task`; other `in_progress` tasks < `max_in_progress`; stage not stopped, blocking stages complete |
| `verifying` | an attempt is open in the run record |
| `review` | a passing record for every gate (`pass`, exit 0, not `infra`/`busy`/`timeout`) |
| `done` | review `verdict: pass` (`checks.review_before_done`); 1–3-line `handoff` when depended on (`checks.handoff_before_done`); run record (`checks.run_record`); granted `new_dependency` approval when a manifest is touched (`dependencies.approval`) |
| `rework` | a `--note`; rounds used < `max_review_rounds`; increments `task.round`, closes the attempt as `fail` |
| `blocked` | a `--note` with reason and need; closes the attempt as `cancelled`, appends an `escalate` event |
| `failed` | a `--note`; closes the attempt as `fail` |
| `done → rework` | granted `reopen_done` approval, plus a note |
| any, `--force` | granted `state_override` approval; recorded with a warning event |

The gate record in `reviews/evidence/*.json` is the only evidence and counts as
passing with exit code 0 and a result other than `infra`, `busy` or `timeout`.
`tools/audit.py` reports what a `done` task is missing.

## Attempts and rounds

- **Attempt:** one run of a task, counted in `runs/<ID>.json`; opens on
  `in_progress`, closes as `pass`, `fail` or `cancelled`, capped by
  `max_attempts_per_task`. At the cap `state.py` refuses another `in_progress`
  and prints the escalation command.
- **Round:** one review, counted by `task.round`; `rework` adds one,
  `max_review_rounds` caps it and a further `rework` is refused.
- A fix inside an attempt is not a new attempt; a rework that leads to a new
  attempt still counts one round. Never reset either counter by editing files.

## Token budget

`budget.max_tokens_per_task` in `policy.json` caps what one task may spend
across all its attempts and sessions (`null` switches it off). The use is
stored per session in `runs/<ID>.json`: the Claude Code Stop hook records its
session from the transcript, every other harness or a human records it with
`tools/usage.py record <ID> --tokens N`. At `budget.warn_at` (default 80 %)
the tools warn; once the budget is used, `tools/state.py` refuses another
`in_progress`, the dispatch plan lists the task as blocked, and the Claude Code
hook tells the agent to stop and report. Continuing needs a granted
`state_override`. `tools/usage.py show` lists the use per task.

## The stage loop

A stage has `exit_criteria`, `exit_gates`, `depends_on` and an `owner_decision`
on the board. It is complete when its blocking stages are complete, every task
in it is `done`, every exit gate has a passing record, and the owner decision
is not `pending`. A `stop` keeps later stages out of "Ready now". The next stage
is planned only after the decision is on the board, not in chat.

## Dispatch

`tools/dispatch.py` is the read-only plan: `limits`, `running`, `waves`,
`blocked`, `conflicts`, `approvals_pending`, `next`. A task is `blocked` (with
the command that records the block) when it used its attempt limit, has no brief
`tasks/<ID>.md`, was claimed by another session, or waits for a dependency or a
stage. Tasks with the same non-empty `parallel_group`, same stage and pairwise
disjoint `scope_write` share a wave; a task without a group is a wave of its
own; groups are packed in board order up to `max_in_progress`. Overlapping
scopes go to `conflicts` and only the first task stays; with
`checks.disjoint_scopes: false` both stay in the wave and the conflict is still
listed. A claimed task is `running`, not a wave member.

## Approvals

`policy.json` lists the required actions: `new_dependency`, `scope_change`,
`merge_to_base`, `release`, `reopen_done`, `protected_path`, `state_override`.

- `approve.py request --action ACTION [--task ID] --note "..."` writes a
  `pending` record; an identical pending request is reused.
- `grant AP-001` / `deny AP-001` set the record and append an `approval` event
  to the task's run record. A granted record is the approval; it does not expire
  and `approve.py` is its only writer.
- The guard reads the store: a dependency-manifest write needs a granted
  `new_dependency` approval (`dependencies.approval: false` turns that off); a
  protected path is refused to every session except a lead, and no approval lets
  a worker write one; `deny` commands are refused for every role, `lead_only`
  commands for worker and reviewer sessions.

## Escalation

Do not retry around a refusal, do not force without an approval.

1. Stop; never edit the board, a run record or an approval by hand.
2. `tools/state.py set <ID> blocked --note "<reason; what is needed>"` — closes
   the attempt as `cancelled` and appends an `escalate` event.
3. State the ask with two options and their consequences; name the decision,
   approval or information that unblocks it.
4. The owner decides with an approval record, a stage decision or a changed
   brief. Work reopens as a new attempt.

Escalate at: an exhausted attempt count, an exhausted review-round count, a
used token budget, a scope conflict, a missing or denied approval, a stopped stage, a policy denial
the task genuinely needs.

## Patterns on the board

| Pattern | Board construct | Enforced by |
|---|---|---|
| Sequential work | `depends_on` | readiness, stage check, `state.py` |
| Concurrent work | same `parallel_group`, disjoint `scope_write` | wave packing, `conflicts` |
| Handoff between tasks | `handoff` (1–3 lines) | `done` checkpoint, `STATUS.md` |
| Stopping a stage | `stages[].owner_decision: "stop"` | readiness, `state.py`, `check.py` |
| Shared runtime resource | `exclusive` + `resources` | gate locks |
| High-risk change | `approvals.actions` + approval record | guard, `state.py`, `audit.py` |
| Who is working | claim (liveness), `owner`/status (plan) | `claim.py`, heartbeat |

## What is not covered

- **Approvals are cooperative evidence, not authentication.** No signature, no
  identity check; whoever can write `reviews/approvals/` can forge a grant, and
  a shell write is outside the guard. Commits and review make it visible.
- **Runs are text files.** `tools/audit.py` compares a run record with the board
  and the evidence folder, not with what happened.
- **Matching is static.** Command patterns see the shell segments after quotes,
  heredocs, assignments and wrappers are stripped — not variables, `eval`, an
  interpreter or a script file. Paths are text: no symlink resolution, and
  case-insensitive on macOS and Windows.
- **The tools are not a sandbox.** A direct write bypasses every checkpoint;
  only the harness sandbox, roles and review make it expensive.
- **The plan is a snapshot.** Re-run `dispatch.py` instead of trusting old
  output. A run record keeps the last 500 events; the board, the reviews and
  git history stay.
