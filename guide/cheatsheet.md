# Cheatsheet

The human's operating manual. The generator drafts and writes; you approve, start tasks and check results. Prompts live only in `prompt/generator.md` › phase I.

## Your role per phase

| Phase | Generator | You |
|---|---|---|
| A Interview | tool check, ≤ 10 questions per round, profile proposal | confirm the profile, the runtime resources and the release path |
| B Recon | repo facts (brownfield) | confirm or correct |
| C + D | architecture, artifact map, task DAG, package map (L), stages, `policy.json` | approve (S: together; M/L: separately) |
| E | roles and protocol, worktrees, claims, runtime rules (M/L) | approve |
| F + G | 3–5 briefs, scaffold, git repo, `.polier-slot` rule, `policy.json`, `docs/orchestration.md`, `AGENTS.md` rules | check file tree, git, structure, policy limits |
| H | `check.py`, cold start, rubric; `audit.py`, `dispatch.py`; L: `boundaries.py`, `contracts.py` | decide on findings |
| I | prompts, checklist | start M01 |

## After the scaffold

- **Git:** `git status --short` is clean; `.gitignore` (incl. `.polier-slot`) and the commit `chore: scaffold` exist; base branch is `main` or as in `board.json`.
- **Structure:** `docs/module-map.md` exists; imports only point downwards; no UI file touches the database. At L: the package map lists every `packages[].path`.
- **AGENTS.md:** commands, git and commit rule, scope and layer rule, runtime rule (ports/DB only from `.polier-slot`, no `kill`/`pkill`); no architecture, no progress.
- **Board:** `schema_version: "1.0"` only if 1.0 fields are used; stages have `exit_gates` and an `owner_decision`; tasks that share e2e, load or a database list the resource in `exclusive`.
- **Generator copy:** if the package sits inside the project (`.generator/`), it is gitignored and ships `tools/manifest.json`, so `check.py` reports drift.
- **Policy:** `policy.json` exists, `version: 1`, limits match the profile (S 3/1/3, M 3/2/3, L 3/3/3 for attempts/in progress/rounds), the manifest list matches the project; `docs/orchestration.md` exists and `AGENTS.md` names `policy.json`, `runs/` and the state commands.

## The dashboard (2.0)

- Start it with `python3 tools/serve.py <project> [--port 8765] [--open] [--token …] [--read-only]`; stop it with Ctrl+C. It needs no dependencies and writes only runtime files under `<git-common-dir>/polier/dashboard/`.
- It shows the same state as `STATUS.md`/`dispatch.py` and drives the same actions: status transitions (`state.py`), claims, approvals (`approve.py`), gates (`gate.py` records), plan edits (validated `board.json` writes) and headless sessions.
- Sessions: `tools/session.py run <ID> --role worker|reviewer|lead [--worktree] [--note "…"]`, then `list`/`show`/`stop`. The provider command, permission mode, allowed tools and model are in the dashboard config; the default is the Claude Code CLI in `-p` stream-json mode with the shipped hooks installed (scope, policy and stop checks apply).
- MCP for an interactive Claude Code session: `claude mcp add polier -- python3 <package>/tools/mcp.py --root .` exposes `polier_snapshot`, `polier_task`, `polier_dispatch`, `polier_show`, `polier_activity`, `polier_approvals`, `polier_claims` and the write tools `polier_state_set`, `polier_gate`, `polier_claim`, `polier_release`.
- Loop unchanged: the dashboard is a control plane, not a second source of truth. `runs/`, `reviews/` and `reviews/approvals/` stay the records; `state.py` stays the only status writer.

## The task loop

Every status change goes through `tools/state.py set <ID> <status>` in a lead session: `in_progress → verifying → review → done`, or `rework`, `blocked`, `failed` with a note. The full model is `prompt/orchestration.md`; the checklists below are the human side of it.

- [ ] Attempts and review rounds are never reset by hand. At a cap `state.py` refuses and names the escalate command: set `blocked` with a note, then ask the owner.
- [ ] Risky actions (new dependency, protected path, merge, release, reopen) need a granted `tools/approve.py` record before the action; `list --status pending` shows open ones.
- [ ] `runs/<ID>.json` is committed with the task and never hand-edited.

## Before every task

- [ ] Pick the next task from "Ready now" in `STATUS.md` or the first wave of `tools/dispatch.py`; at M/L no later-stage task before the blocking stage's exit gates and owner decision are done. A task the plan lists as blocked is not retried.
- [ ] In a lead session (`/pl lead` with the DSH plugin): create the claim and, when the board requires a worktree, the worktree — `python3 <package>/tools/worktree.py start <ID>` (branch + slot + claim). Without the helper: `git worktree add`, then `tools/slot.py acquire`, then `tools/claim.py take <ID> --harness cli --session <name>`.
- [ ] Check the slot: `tools/slot.py show` — ports, `db_name`, `bucket`. Slot 0 is the owner's checkout; never touch its data.
- [ ] Set the task to `in_progress` with `tools/state.py set <ID> in_progress` — never by editing `board.json` — then run `render_status.py` (`/pl render`).
- [ ] Start the worker in that worktree without `/pl lead`. With several tasks in progress or in a worktree: `/pl task <ID>` in that session (it takes/refreshes the claim).
- [ ] Check with `/pl status` that the session shows the right task and scope; `pl_status` shows every live claim of the repo.

## After every task

- [ ] Gate records exist (`reviews/evidence/*.json` from `pl_gate` or `gate.py`), not just "done". A record with `result: infra | busy | timeout` is not evidence — rerun the gate alone; never count a BUSY run as a failed test.
- [ ] Every acceptance criterion evidenced.
- [ ] Diff stays within the scope; no tests changed without approval. Changes from another live claim show up as "foreign changes (task X, harness Y)" — they are not this task's violations.
- [ ] Independent review in a new session (`/pl reviewer` with the plugin), no open blockers (`reviews/Mxx.md`); set `review` before it and `done`/`rework` after it with `tools/state.py`.
- [ ] No placeholders, TODOs or `[UNVERIFIED]`; `tools/research.py check` is green (notes answered and sourced, versions recorded).
- [ ] As lead: merge `task/<ID>`, run the gates again on the base branch, release the claim and the slot and remove the worktree (`python3 <package>/tools/worktree.py finish <ID>` — refuses a dirty checkout), record paths into the task's `evidence`, `state.py set <ID> done`, `handoff` written, `STATUS.md` regenerated, `check.py` (`pl_check`) and `tools/audit.py` green; commit `<ID>: <title>` including `reviews/evidence/` and `runs/<ID>.json`.
- [ ] Next task starts from its brief.

## Stage end

- [ ] Every task in the stage is `done` with evidence; `tools/audit.py` reports no errors for it.
- [ ] Every stage `exit_gates` name has at least one passing record. `render_status.py` shows the missing ones; `render_status.py . --html` writes the same state with tokens and evidence per task as `STATUS.html` (not committed).
- [ ] `exit_criteria` are checked by a human or reviewer, not by a gate.
- [ ] The owner decision is on the board: `owner_decision: "continue"` (or `"stop"`). While it is `pending`, the next stage is not ready and `check.py` errors on any of its tasks that is `in_progress`.
- [ ] For a `stop`: write down what stopped it, leave the tasks pending, commit the board.
- [ ] Then write the next stage's briefs (3–5) and, at L, the package files for packages the stage creates; run `tools/dispatch.py` to confirm the first wave.

## Release checklist

- [ ] `python3 <package>/tools/check.py .` exits 0; `boundaries.py` and `contracts.py check` exit 0 at L.
- [ ] `python3 <package>/tools/release_check.py` exits 0: clean tree, HEAD tagged on the base branch, every released stage done. Previews may use `--allow-untagged`.
- [ ] `CHANGELOG.md` has the version with migration steps; `docs/versions.md` pins every dependency; no `[UNVERIFIED]`.
- [ ] `docs/environments.md` complete: one row per environment, variable names, smoke URL, who may change it.
- [ ] CI builds from the tag; nothing is published from a laptop, a worktree or a dirty checkout. Agents never tag or publish.
- [ ] Deploy to staging, then `python3 <package>/tools/smoke.py --url <staging-url> --path /login --path /`; owner approves production; same tag or artifact.
- [ ] Smoke production; on failure roll back to the previous tag, never re-tag the broken one.

## Red flags

| Symptom | Response |
|---|---|
| No git repo or no diff | `git init`, `.gitignore`, first commit |
| Side strand without contract | contract task in `docs/contracts/` first; both strands depend on it |
| UI imports the store or database | apply `docs/module-map.md`, split the task |
| Package imports outside `may_import` | `tools/boundaries.py` names file and line; fix the import or add the package to `may_import` via an ADR |
| Contract changed without a version bump | bump SemVer, update every dependant or list `contract_followups` |
| Architecture over its profile budget | cut, move details to `docs/`; at L to the package file |
| 20+ briefs before the first code | stop; keep the next 3–5 |
| Generator scores itself | require critic and cold start |
| Two tasks write the same files | split scopes or run sequentially |
| Two sessions on one task | the second claim fails and names the holder; pick another task |
| Agent sets its own task to `done` | only the lead sets `done` with `tools/state.py`, after gates and review |
| Status edited into `board.json` by hand | the run record and the audit disagree; run `tools/state.py set` instead and restore the board |
| Attempt limit reached | `blocked` plus an escalation; the counter is the record, do not reset it |
| Review round limit reached | escalate with the open findings instead of another `rework` |
| Dependency added without a record | `tools/approve.py request` then `grant`; the guard and `audit.py` read the record, not the chat |
| `runs/` or `reviews/approvals/` edited by hand | restore from git; the state tool is the only writer |
| A gate command is denied by the policy | the policy's `commands.deny` must not list it; fix the policy in a reviewed change, no approval overrides a deny |
| `policy.json` fails the check | `version: 1`, known keys only, limits in range; without it the transition table and note rules still hold, the rest warns |
| Write blocked by Polier | expected outside the scope; if the change is right, extend `scope_write` as lead or split the task |
| Write denied with "work in …" | the task has a worktree and this session is in the main checkout; work there |
| Guard never blocks anything | task not `in_progress`, session in lead mode, or plugin not loaded (`/pl status`) |
| Gate prints BUSY | another session holds the exclusive resource; wait or rerun alone, do not retry in parallel |
| Gate record `result: infra` | infrastructure failure, not a test failure: fix the cause, rerun alone |
| "tests passed" as evidence | the record path from `pl_gate`; `check.py` rejects missing, failed or infra records |
| `pkill` a dev server | never stop processes you did not start; use your slot's ports |
| Worktree finish refuses | uncommitted changes; commit or discard them first |
| Generator copy differs from `tools/manifest.json` | update or reinstall the package, then re-run the migration |
| Reviewer never finds anything | sharpen the rubric, require evidence |
| Lead writes feature code | lead plans and merges; workers write |
| Whole docs folder in context | context pack with "Do not read"; at L root + package files only |
| Invented version, package or API | source it, pin it in `docs/versions.md`, or ask |

## When the output is too large

Stop. Keep only files that prevent a concrete class of errors, cut the architecture to one page, reduce briefs to the next 3–5, regenerate `STATUS.md`, and continue only after the cold-start test passes.

## Updating a running project

Update only between stages, when the current stage is `done` and committed — never during a task, and not while M/L workers run. Skip updates that fix nothing you need, and keep the old version for the final stage.

1. Read `CHANGELOG.md` from your `generator_version` up to the new `VERSION`.
2. Replace the package: `./update.sh` (or `--ref <tag>` for a specific version), or swap `.generator/`. `update.sh` prints the drift report of the installed copy first, so local edits are visible before they are overwritten.
3. Reinstall or update once so the copy ships `tools/manifest.json`; then `python3 <package>/tools/drift.py .` reports "local edits or outdated copy" instead of silence.
4. Run `check.py` on the project and apply the migration steps until it is green. A 0.9 project under 1.0 prints migration warnings only; a 1.0 field without `schema_version` is an error.
5. At M/L set `worktrees` (default `required` on a 1.0 board; a 0.9 board stays `recommended`), at L add `schema_version`, `packages`, `stages`, `resources` and `contracts`; budgets only with a `reason`.
6. Optional 1.1 adoption: copy `policy.json` and `docs/orchestration.md` from the templates, add the state/gate/approval rules to `AGENTS.md`, and commit `runs/` from the next task on. Without `policy.json` the project is not broken: the transition table, note rules and `reopen_done`/`state_override` approvals still hold, the rest of the 1.1 checks warn. Once the file exists, every state change goes through `tools/state.py`.
7. Set `generator_version` in `board.json`, run `render_status.py`, commit `chore: update generator to <version>`.

If migration fails, restore the old package; the project is untouched outside that commit.

## Changing the generator

`templates/` is canonical for artifacts, `prompt/generator.md` for the process, `prompt/rubric.md` for quality. Change the generator only for a named class of errors and re-run a reference project (`examples/minimal-cli`, `examples/monorepo-mini` at L). For each release: bump `VERSION`, add a `CHANGELOG.md` entry with migration steps, regenerate `tools/manifest.json` (`python3 tools/manifest.py --write`), update the example's `generator_version` and the README badge, tag `v<version>`.
