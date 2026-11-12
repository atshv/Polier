# Orchestration — Polier next

> How a task of the Polier-next line moves through this repository. The numbers live in `policy.json` (profile S: one task in progress, 3 attempts, 3 review rounds). The full model is `prompt/orchestration.md`.

## Where the state lives

| File | Holds | Written by | Committed |
|---|---|---|---|
| `board.json` | tasks, dependencies, scopes, status | `pl_state` (`tools/state.py`) | yes |
| `factory.json`, `docs/factory.md` | the line and its evidence | `pl_factory` (`tools/factory.py`) | yes |
| `runs/<ID>.json` | attempts, gate, review and state events | `pl_state`, `pl_gate` | yes |
| `reviews/<ID>.md`, `reviews/evidence/` | review rounds, gate records | reviewer, `pl_gate` | yes |
| `reviews/approvals/AP-NNN.json` | owner decisions | `pl_approval` | yes |
| `policy.json` | limits, protected paths, approvals, commands | the owner | yes |
| claims, slots | which session holds which task | `pl_task`, `tools/slot.py` | no |

## The task loop

1. The lead reads `pl_next` and starts the first ready task with `pl_state` → `in_progress`.
2. A fresh subagent of the task's role (`polier:backend-builder`, `polier:architect`, `polier:security-reviewer`) calls `pl_role`, then `pl_task <ID>`, works on branch `task/<ID>` inside the scope, runs every gate with `pl_gate` and `pl_scope_check`, and reports in the brief's YAML format.
3. The lead sets `verifying`, then `review`.
4. A fresh `polier:reviewer` gets the `pl_review` packet and appends a round to `reviews/<ID>.md`.
5. On `verdict: pass` the lead merges `task/<ID>` into the working branch, sets `done` with 1–3 handoff lines, records linked factory items with `pl_factory done`, and commits it in Conventional Commits form with the ID, e.g. `feat(retro): … (M03)` (`AGENTS.md`). On `fail`: `rework` with the findings.

| To | Needs |
|---|---|
| `in_progress` | dependencies done, an attempt left, no other task running, the brief exists |
| `review` | a passing record for every gate of the task |
| `done` | review `pass`; handoff when another task depends on it; a granted `new_dependency` approval when `package.json` changed |

## Branches and review

- One branch per task, `task/<ID>`, from the working branch; only the lead merges, after a passing review and green gates on the merged result.
- Pushes to GitHub and pull requests are the owner's call (`git push` is denied in `policy.json`); releases run in CI from `main` only.

## Approvals

`pl_approval` for `new_dependency` (any change to `package.json`), `scope_change` (a task needs a path outside its scope), `protected_path`, `merge_to_base` (the working branch into `main`) and `release`. A chat "yes" is not an approval. Without a dialog (headless, or a session without the plugin) the owner records the decision with `tools/approve.py grant`.

## Escalation

Stop at an exhausted attempt or round count, a missing or denied approval, or a scope conflict: `pl_state` → `blocked` with the reason and what is needed, then ask the owner with two options. Never edit `board.json`, `runs/` or `reviews/approvals/` by hand.
