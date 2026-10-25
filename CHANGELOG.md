# Changelog

Each release lists what a running project must do to adopt it. Update between stages, never during a task (see `guide/cheatsheet.md`). The current version is in `VERSION`; projects record theirs in `board.json` → `generator_version`.

## 1.0.0

**Parallel projects and monorepos.** 0.9 planned and guarded one project with one active writer well. Running a real project with two harnesses in parallel and planning a monorepo exposed gaps that file-scope guarding cannot catch: shared ports and test databases, gate runs that fail because another session holds a port, snapshots that look like flaky tests, releases from a working folder, missing environment variables, and no common record of who works on what.

**Board 1.0.** `board.json` gets `"schema_version": "1.0"` (opt-in; a 0.9 board omits it and stays valid). Validation is strict per version: a 1.0 field on a 0.9 board is an error that says to set the version, unknown fields are errors.
- Task IDs widen from `M03` to also `P3-02`, `ENG-14`; new optional task fields `package`, `exclusive`, `resources`, `claim` (tooling only), `contract_followups`.
- New board fields: `stages` (exit criteria, exit gates, owner decision, dependencies), `packages` (path, kind, `may_import`), `resources` (slots, port formula, service offsets, `infra_patterns`), `budgets`, `worktrees`, `contracts`.
- `stage` on a task may reference `stages[].id`. `render_status.py` shows per stage: state, exit gates, missing records, owner decision; plus packages and the runtime slot formula. Later-stage tasks are not "ready" while a blocking stage is incomplete, and `check.py` rejects `in_progress` work there.

**Runtime slots and exclusive gates.** Two worktrees can run servers and tests at the same time.
- New `tools/slot.py acquire | release | show | list` and `core/slots.py`: slot 0 is the owner's main checkout, worktrees get the lowest free slot, `.polier-slot` holds ports (`port_base + port_stride·N + service offset`), database name and bucket; registered in `<git-common-dir>/polier/slots.json`.
- `tools/gate.py --exclusive <resource>` (and automatically for a task's `exclusive`) locks the resource in `<git-common-dir>/polier/locks/`; `--lock-wait`/`--lock-ttl`, exit 75 and `result: busy` when it stays held. `pl_gate` honours the same lock.
- Records gain `slot`, `exclusive`, `lock_wait_s`, `result` (`pass | fail | timeout | busy | infra`) and a stale-lock warning. Infrastructure patterns (`ECONNREFUSED`, `EADDRINUSE`, project patterns) are recorded as `infra`; `check.py` rejects `infra`/`busy`/`timeout` records as evidence and says "infrastructure failure, rerun alone" instead of "gate failed".

**Claims and worktrees.** One live session per task, across harnesses.
- New `tools/claim.py take | release | beat | list` and `core/claims.py`: claims in `<git-common-dir>/polier/claims/<task>.json`, live while the heartbeat is younger than 10 minutes. `board.json` is never written by claims. DSH `/pl task` claims and refreshes the heartbeat at most once a minute; `pl_status` lists live claims. Claude Code takes/refreshes the claim when `POLIER_TASK` is set and denies a write while another live session holds the task.
- New `tools/worktree.py start | finish` and `core/scope.py` worktree rule: `worktrees: required` (default at M/L on a 1.0 board; a 0.9 board stays `recommended`) denies a worker write in the main checkout while its task has a worktree ("work in <worktree path>"). `start` creates branch, slot and claim in one step; `finish` refuses uncommitted changes.
- The stop check reports changed files inside another live claim's scope as "foreign changes (task X, harness Y)" instead of blaming the current task. They never block.

**Profile L: monorepo.** Several deployable parts or packages with their own builds, integrated through contracts; L requires `packages`.
- New templates `monorepo-layout.md`, `package-ARCHITECTURE.md`, `package-AGENTS.md`, `contract.md`, `releasing.md`, `environments.md`, `versions.md`, `design-rules.md` and `gates/*.md` (Node/TS, Python, C++/CMake, WASM/Emscripten, Postgres, Playwright, visual diff, load).
- Root `ARCHITECTURE.md` states the system shape; each package gets `ARCHITECTURE.md` (≤ 400 words) and optional `AGENTS.md` (≤ 200); `docs/module-map.md` becomes the package map; briefs list root files plus the package's own files; package files only for packages created in the current stage.
- `check.py` checks package folders, package files, task scopes inside their package (contract paths excepted), a missing or unpinned `docs/versions.md`, and an environment without a smoke URL.
- New `tools/boundaries.py`: import boundaries from `packages[].may_import`, TS/JS/Python/C++ imports, `tsconfig` path aliases; exit 0/1/2; offered as gate `boundaries`.
- New `tools/contracts.py check | list`: JSON Schema 2020-12 contracts with valid/invalid fixtures, SemVer rules (major for a removed or renamed field), dependants and `contract_followups`.
- Profile-dependent budgets replace ad-hoc overrides: architecture 600/700/800, AGENTS 300/350/400, STATUS 300/500/900, briefs 800/800/900, package files 400/200. A board override needs a `reason`.

**Release and smoke.** `templates/releasing.md` and `templates/environments.md` describe trunk-based flow, tags, CI-only release, rollback and the environment × variable checklist (names only). New `tools/release_check.py` (dirty tree, untagged HEAD, tag not on the base branch, released-stage tasks not done; `--allow-untagged` for previews) as gate `release-clean`, and `tools/smoke.py` (URL status paths, headers only as `--header "Name: env:VARIABLE"`, recorded via `gate.py`). Generated `AGENTS.md` says: agents never publish; releases run in CI from tags.

**UI briefs.** `templates/task-brief.md` has an optional "UI specification" section: target values in px/ms/tokens, all applicable states, "do not", screenshot evidence. `templates/design-rules.md` is the binding token/state/accessibility reference. The rubric has a 13th criterion: a UI task without target values fails.

**Drift detection.** `tools/manifest.json` lists the SHA-256 of every shipped file; `tools/drift.py` compares the project-local copy (`.generator/`) with it and `update.sh` prints the drift report (the files that differ) before updating. `check.py` warns "local edits or outdated copy" and names the files. Extra files next to the copy are ignored.

**Guard extras.** `kill`, `pkill`, `killall` and `xargs kill` in a worker command get a warning (Claude Code: `ask`; DSH: one message per turn) — never a denial. Guarded paths compare case-insensitively on macOS and Windows, where the file system does.

**Compatibility.** No field removed; a valid 0.9 board still validates and `check.py` reports the version difference as a migration warning. Validation is now strict per schema version, so unknown fields are errors — a board with invented fields drops them or moves them anywhere outside `board.json`. `drift.py`, `slot.py`, `claim.py`, `worktree.py`, `boundaries.py`, `contracts.py`, `release_check.py`, `smoke.py` and `manifest.py` are additive. The core gains `core/slots.py`, `core/locks.py`, `core/claims.py` and `core/boundaries.py`; the DSH guard mirror in `adapters/dsh/lib/project.mjs` gains the worktree rule, case-insensitive comparison and kill detection, tested against `core/tests/write_cases.json`.

**Migration:** S and M projects need nothing. To adopt the new features: add `resources` to the board, `.polier-slot` to `.gitignore` and a `tools/dev/setup` that reads `.polier-slot`; add `"exclusive": ["e2e"]` (or `db`, `load`) to tasks whose gates share a resource; at M/L a 1.0 board defaults `worktrees` to `required`, while a 0.9 board stays on `recommended`, so an existing project is unchanged until the owner sets `required` after migrating. L projects: set `"schema_version": "1.0"`, add `packages[]` (with `may_import`), `stages[]` and `resources`, move to one package per folder with `ARCHITECTURE.md` and optional `AGENTS.md`, declare `contracts[]` with schemas and fixtures, and use `worktrees: required`. Plugin users: `git pull` in the clone, run `dsh plugin --profile <name> add ./polier` again and restart; one update is needed to get `tools/manifest.json` for drift detection. Claude Code users: replace the package copy (`./install.sh claude` or `./update.sh claude`); the hook entries stay the same, set `POLIER_TASK` so the hook claims the task (a second live claim now denies writes), and expect `ask` on process-killing commands and foreign changes in the stop message. Skill-only users: `./update.sh`; reinstall once for the manifest. Projects still on 0.9: `check.py` under 1.0 passes or prints only migration warnings (generator version, missing manifest), and schema errors only appear when a 1.0 field is used without `schema_version`.

## 0.9.0

**Core split from the harness.** The enforcement rules now live in `core/`, a Python package without any DeepSeek Harness code, so later adapters (Claude Code, git hooks) can use the same rules.

- `core/`: `check_write` (guard decision), `check_stop` and `scope_check` (changed files against a task), `run_gate` (gate records), `verify_evidence`, `load_board`, `pick_task`, `active_tasks`, `ready_tasks`. Python 3.9+, standard library only, own tests in `core/tests/`.
- The DSH plugin moved from `dsh/` to `adapters/dsh/`; `package.json` points there. Its synchronous guard keeps a JavaScript mirror of `check_write`; both are tested against one decision table, `core/tests/write_cases.json`.
- `tools/gate.py`, `tools/scope_check.py` and `tools/check.py` are thin command-line wrappers around `core/`; paths, options, output and exit codes are unchanged.
- **Claude Code adapter** in `adapters/claude-code/`: a `PreToolUse` hook checks `Write`, `Edit`, `MultiEdit`, `NotebookEdit` and the files a `Bash` command visibly writes (new `core/shell.py`); a `Stop` hook runs the stop check and sends violations back to Claude. Roles and settings come from `POLIER_*` environment variables. Example `settings.example.json`, install guide and tests with simulated hook events.
- README lists what the guard does not cover.
- `install.sh` no longer copies `__pycache__` folders and leaves out the new test folders.
- Unchanged: plugin behaviour, tool names, `/pl`, messages, `board.json` fields. The guard and the stop check keep their slightly different rule order (the guard lets `reviews/evidence/` through before `scope_write_forbidden`, the stop check checks `scope_write_forbidden` first).

**Migration:** set `generator_version` to `0.9.0`. Plugin users: `git pull` in the clone, then run `dsh plugin --profile <name> add ./polier` again and restart the harness. Skill-only users: `./update.sh`. Projects that call `tools/gate.py` keep working. Claude Code: optional, see `adapters/claude-code/README.md`.

## 0.8.0

**Renamed to Polier.** The project was the "Prompt Generator"; it now plans and enforces, so it is called Polier (German for site foreman).

- Repository `atshv/polier` (GitHub redirects the old `atshv/prompt-generator`), package `dsh-polier`, plugin row and skill `polier`.
- Tools `pl_status`, `pl_gate`, `pl_scope_check`, `pl_check` (were `pg_*`); human command `/pl` (was `/pg`).
- Messages start with `Polier:`. `install.sh` and `update.sh` install the skill as `polier`.
- Unchanged: file layout, `board.json` fields (including `generator_version`), the Python tools and their output.

**Migration:** set `generator_version` to `0.8.0`. In each project's `AGENTS.md`, replace `pg_gate` with `pl_gate` (and any other `pg_*`). Plugin users: `dsh plugin --profile <name> remove dsh-prompt-generator`, then `dsh plugin --profile <name> add ./polier`. Skill-only users: delete `~/.dsh/skills/prompt-generator/` and run `./install.sh` again. Use `/pl` instead of `/pg`.

## 0.7.1

- Plugin: `/pg reviewer` makes a session write only under `reviews/` (with or without a running task).
- `prompt/generator.md`: tool check detects the plugin; the gate rule in `AGENTS.md` names `pg_gate` or the real `gate.py` path; the human checklist sets each task `in_progress` before the worker starts; start and review prompts use `pg_status`, `pg_gate`, `pg_scope_check` and gate records.
- `guide/cheatsheet.md`: new "Before every task" checklist, evidence and `/pg` steps after every task, red flags for the guard.
- GitHub workflow runs `npm test` and `check.py` on the example for every push to `main` and every pull request.
- Example: gate rule in `AGENTS.md` updated; leftover `brief.md` and `review-feedback.md` removed (`project-input.md` and `reviews/M03.md` are the current versions).

**Migration:** set `generator_version` to `0.7.1`. Optional: take the new gate rule from `templates/AGENTS.template.md`; use `/pg reviewer` for review sessions.

## 0.7.0

**DeepSeek Harness plugin.** The package is now also an installable DSH plugin (`dsh plugin --profile <name> add …`, see `README.md`). It registers the skill with its files resolved inside the package and adds:

- a write guard: while a task is `in_progress`, a worker session may write only inside that task's `scope_write` (minus `scope_write_forbidden`); `board.json`, `STATUS.md` and `tasks/` are lead-owned, `reviews/evidence/` is always writable. Config `enforce: deny | ask | off`.
- a stop check: before a turn ends, the git diff is compared with the scope. Out-of-scope changes, including those made through `bash`, are sent back to the agent (max. 2 reminders per turn).
- tools `pg_status`, `pg_gate`, `pg_scope_check`, `pg_check`.
- the human command `/pg` (`status`, `lead`, `worker`, `off`, `task <ID>`, `render`). Roles live in memory; after a harness restart every session is a worker again.

**Tools.**

- New `tools/scope_check.py`: changed files (modified, staged, untracked, deleted, both sides of a rename) against the running task's scope. Exit 0/1/2, `--json`.
- `tools/gate.py` writes a new log and a JSON record per run (command, exit code, times, commit, dirty flag, SHA-256 of the log) and never overwrites. The last output line is `record: <path>`. New `--shell "<command>"`.
- `tools/check.py` verifies records for `done` tasks: file exists, belongs to the task, log unchanged, exit code 0, every listed gate covered. A record made on a commit outside `HEAD`'s history warns. Free-text evidence only warns.
- Earlier in this cycle: `install.sh` uses `tar` instead of `rsync`; optional `handoff` per task, shown by `render_status.py` under "Ready now"; `check.py` warns on `STATUS.md` over 300 words, context packs over about 15k tokens and done tasks without handoff.
- Tests: `npm test` (plugin against the real DSH tool registry, Python `unittest` for the tools).

**Migration:** set `generator_version` to `0.7.0`. Replace the gate line in `AGENTS.md` with the one from `templates/AGENTS.template.md`. From now on put the record paths from `gate.py`/`pg_gate` into `evidence`; old free-text evidence keeps passing with a warning. Commit `reviews/evidence/`. To use the plugin, install it and use `/pg lead` in sessions that plan, merge or edit the board.

## 0.6.0

- Package reorganised: `prompt/` (generator, rubric, DSH mapping), `guide/` (cheatsheet), root keeps entry points (`SKILL.md`, `README.md`, `CHANGELOG.md`, `VERSION`, `install.sh`, `update.sh`).
- `prompt/generator.md` states which paths belong to the package and which to the project.

**Migration:** projects: set `generator_version` to `0.6.0`. Chat users: attach `prompt/generator.md` and `prompt/rubric.md` instead of the root files. Skill installs: run `./update.sh`.

## 0.5.6

- `install.sh` and `update.sh` accept the target `claude` (`~/.claude/skills`) for Claude Code; DSH stays the default.

**Migration:** set `generator_version` to `0.5.6`.

## 0.5.5

- `install.sh` and `update.sh` target the DeepSeek Harness only (`~/.dsh/skills` or a given path).

**Migration:** set `generator_version` to `0.5.5`.

## 0.5.4

- `install.sh` and `update.sh` install, update or roll back the skill from the shell, optionally pinned to a tag.

**Migration:** set `generator_version` to `0.5.4`.

## 0.5.3

- `STATUS.md` starts with a "Ready now" list: pending tasks whose dependencies are done.
- `check.py` rejects `done` tasks without `evidence`.
- Interview questions offer a recommended default first.
- `board.json` records `generator_version`; `check.py` warns when it differs from the package.

**Migration:** add `"generator_version": "0.5.3"` to `board.json`; fill `evidence` for every `done` task; run `render_status.py`.

## 0.5.2

- `dsh.md` maps every phase to a DeepSeek Harness tool, with fallbacks; install as a DSH skill.
- All documents tightened; no rule changed.

**Migration:** none.

## 0.5.1

- `SKILL.md` entry point for installation as an agent skill.
- `check.py` cross-checks artifacts: briefs match their board entry (ID, title, acceptance IDs, `**Scope:**` line, `satisfies`), every `AD-n`/`ADR-nnnn` reference exists, `STATUS.md` matches `board.json`.
- Traceability: definition-of-done items `D1..Dn` in `docs/quality.md`, covered by the new task field `satisfies`.

**Migration:** run `render_status.py`; align briefs with the board; optionally number the definition of done and add `satisfies` (without D-IDs, `check.py` only warns).

## 0.5.0

- Package translated to English; default project language English.
- Reviews stored in `reviews/<ID>.md`; briefs always `tasks/<ID>.md`.
- `check.py` requires `.gitignore` and `base_branch`; layer names in `docs/module-map.md` are checked in English (UI, logic, data).

**Migration:** projects from 0.4 keep running with the 0.4 package; switching requires English layer names in `docs/module-map.md`, a `.gitignore`, and moving review files to `reviews/`.

## 0.4.0

German original.
