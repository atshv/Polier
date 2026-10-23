# Changelog

Each release lists what a running project must do to adopt it. Update between stages, never during a task (see `guide/cheatsheet.md`). The current version is in `VERSION`; projects record theirs in `board.json` → `generator_version`.

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
