# Cheatsheet

The human's operating manual. The generator drafts and writes; you approve, start tasks and check results. Prompts live only in `generator.md` › phase I.

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

## After every task

- [ ] Gate output seen, not just "done".
- [ ] Every acceptance criterion evidenced.
- [ ] Diff stays within the scope; no tests changed without approval.
- [ ] Independent review in a new session, no open blockers (`reviews/Mxx.md`).
- [ ] No placeholders, TODOs or `[UNVERIFIED]`.
- [ ] `STATUS.md` regenerated; commit `<ID>: <title>`.
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
| Reviewer never finds anything | sharpen the rubric, require evidence |
| Lead writes feature code | lead plans and merges; workers write |
| Whole docs folder in context | context pack with "Do not read" |
| Invented version, package or API | source it, mark `[UNVERIFIED]`, or ask |

## When the output is too large

Stop. Keep only files that prevent a concrete class of errors, cut the architecture to one page, reduce briefs to the next 3–5, regenerate `STATUS.md`, and continue only after the cold-start test passes.

## Changing the generator

`templates/` is canonical for artifacts, `generator.md` for the process, `rubric.md` for quality. Change the generator only for a named class of errors, re-run a reference project afterwards, and bump the version in `README.md` and `generator.md`.
