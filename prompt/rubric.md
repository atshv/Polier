# Quality Rubric and Lint

A generated project is good when an outside agent can work from it without asking. Terms (gate, exclusive gate, runtime slot, claim, stage, contract, cold-start test) are defined in `prompt/generator.md`.

## 1. Criteria

Score each criterion **0 or 1**. **B** marks a blocker: it prevents approval regardless of the total.

| # | Criterion | Check | B |
|---|---|---|---|
| 1 | Purpose, users, value | 2–3 sentences say what the system does, for whom, and how success is measured. | B |
| 2 | Scope and non-goals | Both are listed explicitly. | – |
| 3 | Testable acceptance | Every requirement is WHEN–THEN and covered by a gate or test. | B |
| 4 | Context pack | Each brief names what to read, what not to read, and a token budget; at L it lists root files plus the package's own files only. | – |
| 5 | Exact specifications | Fields, types, limits, paths and texts are concrete, not adjectives. | – |
| 6 | Edge cases | Empty input, duplicates, invalid values, lost connection, repeated actions are covered. | – |
| 7 | Gates | Build, test and acceptance commands with expected output exist; at L commands come from the gate catalogue or the manifests. | B |
| 8 | Architecture spine | `ARCHITECTURE.md` within the profile budget (600/700/800 words), 3–7 invariants (AD IDs), non-goals, module or package structure, references. | – |
| 9 | Roles and scopes | Topology fits the profile; each task has one writer and a disjoint scope; M/L work happens in worktrees and one claim per task. | – |
| 10 | Review independence | Reviewer, reviewer inputs and escalation are defined. | B |
| 11 | Size budgets | All artifacts within budget (per profile); package `ARCHITECTURE.md` ≤ 400 and package `AGENTS.md` ≤ 200 words at L; no duplicated content. | – |
| 12 | Nothing invented | Libraries, APIs, versions and paths are sourced or marked `[UNVERIFIED]`; at L every manifest dependency is pinned in `docs/versions.md`. | – |
| 13 | UI tasks have numbers | A task that touches UI paths has the UI specification section with target values in px/ms/tokens, all applicable states and screenshot evidence. | **B** if the task touches UI |

**Pass:** ≥ 12/13 and no blocker. Otherwise fix and re-check; after two rounds the human decides.

## 2. Lint

*(check.py)* marks what `tools/check.py` verifies; *(contracts.py)* and *(boundaries.py)* mark the L tools; the rest needs a reviewer. A 0.9 project that runs 1.0 prints migration warnings only — they are findings here.

- [ ] Mandatory files present, including `.gitignore` *(check.py)*; `.polier-slot` and a project-local generator copy are ignored (reviewer).
- [ ] `board.json` has the right schema for its version: 1.0 fields only with `"schema_version": "1.0"`, 0.9 boards unchanged *(check.py)*.
- [ ] `ARCHITECTURE.md` within the profile budget (S/M/L: 600/700/800) *(check.py)*; sections 1–8 present. At L: system shape only, package detail in the package files.
- [ ] `AGENTS.md` within the profile budget (300/350/400, warning) *(check.py)*; commands, scope, commit rule *(check.py)* and the runtime rules (ports from `.polier-slot`, no `kill`/`pkill`, release rule at L); no architecture or progress.
- [ ] `docs/module-map.md` defines layers *(check.py requires the words UI, logic and data for every profile)*; at L also the package map (path, kind, `may_import`), with every `packages[].path` listed *(check.py, warning)*; folders and import direction.
- [ ] `board.json`: valid, mandatory task fields, `base_branch`, complexity ≤ 6, no unknown dependencies, no cycles, no overlapping write scopes in a parallel group *(check.py)*.
- [ ] Task IDs use a form allowed by the schema version (`M03` at 0.9; also `P3-02`, `ENG-14` at 1.0) *(check.py)*.
- [ ] Stages: every stage has `exit_gates` *(check.py, warning)*, no task works in a stopped or not-yet-unblocked stage *(check.py)*, owner decisions are on the board, not in chat.
- [ ] Packages (L): `packages[]` present *(check.py)*, every folder exists or is created by a task *(check.py)*, each has `ARCHITECTURE.md` ≤ 400 *(check.py)* and optional `AGENTS.md` ≤ 200 *(check.py, warning)*, every task's `scope_write` stays inside its package or a contract path *(check.py)*, imports respect `may_import` *(boundaries.py)*.
- [ ] Budgets: board overrides carry a `reason` *(check.py)*.
- [ ] Briefs match the board: ID, title, acceptance IDs, scope, `satisfies` *(check.py)*.
- [ ] UI briefs have target values in px/ms/tokens, every applicable state and screenshot evidence; words like "nicer", "cleaner", "faster" without a number are a finding.
- [ ] Every `AD-n` and `ADR-nnnn` reference exists *(check.py)*.
- [ ] Every definition-of-done item `D1..Dn` is covered by a task *(check.py)*.
- [ ] `STATUS.md` matches `board.json` *(check.py)*; per stage it shows state, exit gates and the owner decision.
- [ ] Every `done` task has a passing `tools/gate.py` record for each of its gates, with an unchanged log; `infra`, `busy` and `timeout` records are rejected *(check.py; free-text evidence only warns)*.
- [ ] `docs/environments.md`: each environment has a smoke URL *(check.py, warning)*; variable names only, no values.
- [ ] `docs/versions.md`: every manifest dependency is pinned with source URL and date *(check.py, L, warnings)*.
- [ ] Contracts (L): every board contract has a schema, at least one valid and one invalid fixture, a SemVer version and its dependants *(contracts.py)*; a changed schema has the required bump *(contracts.py)*.
- [ ] Generator copy matches `tools/manifest.json` — "local edits or outdated copy" names the files *(check.py, warning)*.
- [ ] No placeholders or TODOs *(check.py)*; no `[UNVERIFIED]` in critical paths.
- [ ] Internal links resolve *(check.py)*; named paths exist or are marked new.
- [ ] Git repo initialised *(check.py, warning)* with a first commit.
- [ ] Every acceptance criterion has a gate or named test.
- [ ] Every brief has a context pack ("Read exactly", "Do not read") and a stop/budget section.
- [ ] Every task needing a shared runtime resource lists it in `exclusive`; every gate that needs ports or a database reads them from `.polier-slot`.
- [ ] No task mixes UI and data access; each names its layer or package.
- [ ] No monolith files; no secrets or credentials in files or bundles.

## 3. Critic prompt

Same subagent as the cold start (§4), continued after it.

```text
You are an independent critic. You did not write this project; do not rewrite it.

Read only: ARCHITECTURE.md, AGENTS.md, STATUS.md, board.json, tasks/*.md,
docs/quality.md, docs/module-map.md (if present), docs/versions.md, docs/environments.md,
package ARCHITECTURE.md/AGENTS.md files (profile L only).

Score the 13 criteria of prompt/rubric.md. Look especially for:
1. architecture over its profile budget or details that belong elsewhere
2. acceptance criteria without gate or test
3. tasks without scope, with cycles or overlapping write paths
4. missing context packs or budgets
5. roles or permissions that do not fit the profile
6. invented versions, paths or APIs
7. contradictions between architecture, briefs and board
8. missing git repo, .gitignore or first commit
9. mixed layers (UI accesses data, logic imports UI)
10. profile L: package files missing or over budget, scope_write leaving its package,
    contract without version or fixtures, may_import not matching the package map
11. UI tasks with adjectives instead of target values in px/ms/tokens
12. stages without exit gates, no owner decision, or later-stage work already running
13. exclusive resources not declared on tasks whose gates share ports or a database

Output: table | # | criterion | 0/1 | blocker | finding | file | fix |,
then total, blockers, top three improvements.
No rewrites. No score without findings. No finding without file and line.
```

## 4. Cold-start test

```text
You are new on this project. You have only ARCHITECTURE.md, AGENTS.md,
STATUS.md and tasks/M01.md (profile L: plus the package's ARCHITECTURE.md and AGENTS.md).

Answer without asking back:
1. The project goal in one sentence.
2. M01's scope and what is explicitly out.
3. Which files you would change, and which not.
4. Which commands you would run and what you expect.
5. What information is missing for a plan.
6. Which additional file you would need.
7. Which layer or package the change belongs to.
8. Which gate would prove the change, and whether it needs an exclusive resource.

Be brief. Invent nothing.
```

**Pass:** no blocking question; correct files, layer/package and gates; no new decision needed. Each question back is a finding: close real gaps in the brief (or, if every module needs it, in the architecture) and re-test.

## 5. Anti-gaming

- Authors never score their own work.
- The critic sees artifacts only: no reasoning, self-assessment or chat history.
- Every finding needs file, criterion and evidence; "looks good" is not a finding.
- Count fixed blockers, not scores. A critic that never finds anything means the rubric is too soft.
