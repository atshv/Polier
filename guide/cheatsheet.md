# Cheatsheet

The human's operating manual. The generator drafts and writes; you approve, start tasks and check results. Prompts live only in `prompt/generator.md` › phase I.

## Your role per phase

| Phase | Generator | You |
|---|---|---|
| 0 Interview | tool check, ≤ 10 questions per round, profile proposal | confirm the profile |
| B Recon | repo facts (brownfield) | confirm or correct |
| C + D | architecture, artifact map, task DAG | approve (S: together; M/L: separately) |
| E | roles and protocol (M/L) | approve |
| F + G | 3–5 briefs, scaffold, git repo | check file tree, git, structure |
| H | `check.py`, cold start, rubric | decide on findings |
| I | prompts, checklist | start M01 |

## After the scaffold

- **Git:** `git status --short` is clean; `.gitignore` and the commit `chore: scaffold` exist; base branch is `main` or as in `board.json`.
- **Structure:** `docs/module-map.md` exists; imports only point downwards; no UI file touches the database.
- **AGENTS.md:** commands, git and commit rule, scope and layer rule; no architecture, no progress.

## Before every task

- [ ] In a lead session (`/pg lead` with the DSH plugin): set the task to `in_progress` in `board.json`, run `render_status.py` (`/pg render`).
- [ ] Start the worker in a new session without `/pg lead`. With several tasks in progress or in a worktree: `/pg task <ID>` in that session.
- [ ] Check with `/pg status` that the session shows the right task and scope.

## After every task

- [ ] Gate records exist (`reviews/evidence/*.json` from `pg_gate` or `gate.py`), not just "done".
- [ ] Every acceptance criterion evidenced.
- [ ] Diff stays within the scope; no tests changed without approval.
- [ ] Independent review in a new session (`/pg reviewer` with the plugin), no open blockers (`reviews/Mxx.md`).
- [ ] No placeholders, TODOs or `[UNVERIFIED]`.
- [ ] As lead: record paths into the task's `evidence`, status `done`, `handoff` written, `STATUS.md` regenerated, `check.py` (`pg_check`) green; commit `<ID>: <title>` including `reviews/evidence/`.
- [ ] Next task starts from its brief.

## Red flags

| Symptom | Response |
|---|---|
| No git repo or no diff | `git init`, `.gitignore`, first commit |
| Side strand without contract | contract task in `docs/contracts/` first; both strands depend on it |
| UI imports the store or database | apply `docs/module-map.md`, split the task |
| Architecture > 800 words | cut, move details to `docs/` |
| 20+ briefs before the first code | stop; keep the next 3–5 |
| Generator scores itself | require critic and cold start |
| Two tasks write the same files | split scopes or run sequentially |
| Agent sets its own task to `done` | only the lead sets `done`, after gates and merge |
| Write blocked by prompt-generator | expected outside the scope; if the change is right, extend `scope_write` as lead or split the task |
| Guard never blocks anything | task not `in_progress`, session in lead mode, or plugin not loaded (`/pg status`) |
| "tests passed" as evidence | the record path from `pg_gate`; `check.py` rejects missing or failed records |
| Reviewer never finds anything | sharpen the rubric, require evidence |
| Lead writes feature code | lead plans and merges; workers write |
| Whole docs folder in context | context pack with "Do not read" |
| Invented version, package or API | source it, mark `[UNVERIFIED]`, or ask |

## When the output is too large

Stop. Keep only files that prevent a concrete class of errors, cut the architecture to one page, reduce briefs to the next 3–5, regenerate `STATUS.md`, and continue only after the cold-start test passes.

## Updating a running project

Update only between stages, when the current stage is `done` and committed — never during a task, and not while M/L workers run. Skip updates that fix nothing you need, and keep the old version for the final stage.

1. Read `CHANGELOG.md` from your `generator_version` up to the new `VERSION`.
2. Replace the package: `./update.sh` (or `--ref <tag>` for a specific version), or swap `.generator/`.
3. Run `check.py` on the project and apply the migration steps until it is green.
4. Set `generator_version` in `board.json`, run `render_status.py`, commit `chore: update generator to <version>`.

If migration fails, restore the old package; the project is untouched outside that commit.

## Changing the generator

`templates/` is canonical for artifacts, `prompt/generator.md` for the process, `prompt/rubric.md` for quality. Change the generator only for a named class of errors and re-run a reference project. For each release: bump `VERSION`, add a `CHANGELOG.md` entry with migration steps, update the example's `generator_version` and the README badge, tag `v<version>`.
