# UX flows: Polier next

> Station 3 (design). Polier has no screens; its interface is the owner's plain language, the `pl_*` tools and the Python commands underneath. Only the command interface applies (`DES-15`).

## Flows

| Story | Owner says | Agent calls | Result | Error path |
| --- | --- | --- | --- | --- |
| US1 | "Does Polier still work better than without it?" | `npm run evals` (maintainer, not the agent) | score per case with and without Polier, delta, exit code | a case below threshold names itself; exit 1 |
| US2 | "What went wrong in my projects?" | `tools/retro.py <folders>` | `retro.md` with error classes | folder without records: skipped with reason |
| US3 | "Add export to the shipped app." | `pl_change new`, then `pl_approval scope_change`, `pl_change apply` when the tasks are done | proposal, linked tasks, delta merged into the living docs | owner rejects: proposal stays `rejected`, nothing merges |
| US4 | "Fix the crash on empty input." | `pl_quick` | one task with brief, gates and review, no station reopened | touches platforms, traits, data model or a must item: refused with the proposal path |

## Commands

| Command | Flags | Output | Exit codes |
| --- | --- | --- | --- |
| `npm run evals` | passes extra flags to `claude plugin eval`, e.g. `-- --case close-station` | progress and summary table; `evals/results/<time>/` | 0 every case ≥ threshold, 1 a case below or a load error, 2 cost ceiling hit |
| `tools/retro.py FOLDER…` | `--json`, `--write PATH`, `--since YYYY-MM-DD` | markdown report on stdout (or `PATH`); `--json` an object with `classes[]` and `skipped[]` | 0 report written, 1 no folder had records, 2 usage |
| `tools/change.py new TITLE` | `--root`, `--json` | creates `changes/C<NN>/proposal.md` from the template, prints its ID | 0 ok, 2 usage or no line |
| `tools/change.py show [ID]` | `--root`, `--json` | one proposal with status, linked tasks, approval; without ID all of them | 0 ok, 1 unknown ID |
| `tools/change.py link ID --task T…` | `--root` | links board tasks to the proposal | 0 ok, 1 unknown task or proposal |
| `tools/change.py apply ID` | `--root`, `--by NAME` | merges the delta into the named docs, archives the proposal, prints what changed | 0 merged, 1 approval missing, a linked task not done or a delta anchor not found |
| `tools/quick.py new TITLE --scope PATH…` | `--gate NAME…`, `--role ROLE`, `--root`, `--json` | adds one `track: quick` task to `board.json` and writes `tasks/<ID>.md` | 0 created, 1 refused (reason and proposal path), 2 usage |
| `pl_change` | action `new`, `show`, `link`, `apply` with the flags above | JSON with `next` | tool error with the refusal |
| `pl_quick` | `title`, `scope`, `gates`, `role` | JSON with the task ID and `next` | tool error with the refusal |

Every command prints what happened and what comes next; `--json` prints one object, nothing else on stdout. `apply` and `quick.py new` change records and run only in a lead session or headless.
