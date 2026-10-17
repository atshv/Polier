# Changelog

Each release lists what a running project must do to adopt it. Update between stages, never during a task (see `guide/cheatsheet.md`). The current version is in `VERSION`; projects record theirs in `board.json` → `generator_version`.

## Unreleased

- `install.sh` copies with `tar` instead of `rsync`, so it also runs on systems without `rsync`.

**Migration:** none.

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
