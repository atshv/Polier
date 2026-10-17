# Quality Rubric and Lint

A generated project is good when an outside agent can work from it without asking. Terms (gate, task passed, cold-start test) are defined in `generator.md`.

## 1. Criteria

Score each criterion **0 or 1**. **B** marks a blocker: it prevents approval regardless of the total.

| # | Criterion | Check | B |
|---|---|---|---|
| 1 | Purpose, users, value | 2–3 sentences say what the system does, for whom, and how success is measured. | B |
| 2 | Scope and non-goals | Both are listed explicitly. | – |
| 3 | Testable acceptance | Every requirement is WHEN–THEN and covered by a gate or test. | B |
| 4 | Context pack | Each brief names what to read, what not to read, and a token budget. | – |
| 5 | Exact specifications | Fields, types, limits, paths and texts are concrete, not adjectives. | – |
| 6 | Edge cases | Empty input, duplicates, invalid values, lost connection, repeated actions are covered. | – |
| 7 | Gates | Build, test and acceptance commands with expected output exist. | B |
| 8 | Architecture spine | `ARCHITECTURE.md` ≤ 800 words, 3–7 invariants (AD IDs), non-goals, module structure, references. | – |
| 9 | Roles and scopes | Topology fits the profile; each task has one writer and a disjoint scope. | – |
| 10 | Review independence | Reviewer, reviewer inputs and escalation are defined. | B |
| 11 | Size budgets | All artifacts within budget; no duplicated content. | – |
| 12 | Nothing invented | Libraries, APIs, versions and paths are sourced or marked `[UNVERIFIED]`. | – |

**Pass:** ≥ 11/12 and no blocker. Otherwise fix and re-check; after two rounds the human decides.

## 2. Lint

*(check.py)* marks what `tools/check.py` verifies; the rest needs a reviewer.

- [ ] Mandatory files present, including `.gitignore` *(check.py)*.
- [ ] `ARCHITECTURE.md` ≤ 800 words *(check.py)*; sections 1–8 present.
- [ ] `AGENTS.md` ≤ 400 words *(check.py, warning)*; commands, scope and commit rule *(check.py)*; no architecture or progress.
- [ ] `docs/module-map.md` defines layers *(check.py)*, folders and import direction.
- [ ] `board.json`: valid, mandatory task fields, `base_branch`, complexity ≤ 6, no unknown dependencies, no cycles, no overlapping write scopes in a parallel group *(check.py)*.
- [ ] Briefs match the board: ID, title, acceptance IDs, scope, `satisfies` *(check.py)*.
- [ ] Every `AD-n` and `ADR-nnnn` reference exists *(check.py)*.
- [ ] Every definition-of-done item `D1..Dn` is covered by a task *(check.py)*.
- [ ] `STATUS.md` matches `board.json` *(check.py)*.
- [ ] Every `done` task has evidence *(check.py)*.
- [ ] No placeholders or TODOs *(check.py)*; no `[UNVERIFIED]` in critical paths.
- [ ] Internal links resolve *(check.py)*; named paths exist or are marked new.
- [ ] Git repo initialised *(check.py, warning)* with a first commit.
- [ ] Every acceptance criterion has a gate or named test.
- [ ] Every brief has a context pack ("Read exactly", "Do not read") and a stop/budget section.
- [ ] No task mixes UI and data access; each names its layer.
- [ ] No monolith files; no secrets or credentials in files or bundles.

## 3. Critic prompt

Same subagent as the cold start (§4), continued after it.

```text
You are an independent critic. You did not write this project; do not rewrite it.

Read only: ARCHITECTURE.md, AGENTS.md, STATUS.md, board.json, tasks/*.md,
docs/quality.md (if present).

Score the 12 criteria of rubric.md. Look especially for:
1. architecture > 800 words or details that belong elsewhere
2. acceptance criteria without gate or test
3. tasks without scope, with cycles or overlapping write paths
4. missing context packs or budgets
5. roles or permissions that do not fit the profile
6. invented versions, paths or APIs
7. contradictions between architecture, briefs and board
8. missing git repo, .gitignore or first commit
9. mixed layers (UI accesses data, logic imports UI)

Output: table | # | criterion | 0/1 | blocker | finding | file | fix |,
then total, blockers, top three improvements.
No rewrites. No score without findings. No finding without file and line.
```

## 4. Cold-start test

```text
You are new on this project. You have only ARCHITECTURE.md, AGENTS.md,
STATUS.md and tasks/M01.md.

Answer without asking back:
1. The project goal in one sentence.
2. M01's scope and what is explicitly out.
3. Which files you would change, and which not.
4. Which commands you would run and what you expect.
5. What information is missing for a plan.
6. Which additional file you would need.
7. Which layer the change belongs to.

Be brief. Invent nothing.
```

**Pass:** no blocking question; correct files, layer and gates; no new decision needed. Each question back is a finding: close real gaps in the brief (or, if every module needs it, in the architecture) and re-test.

## 5. Anti-gaming

- Authors never score their own work.
- The critic sees artifacts only: no reasoning, self-assessment or chat history.
- Every finding needs file, criterion and evidence; "looks good" is not a finding.
- Count fixed blockers, not scores. A critic that never finds anything means the rubric is too soft.
