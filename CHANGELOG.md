# Changelog

What changed per version. Polier is not released yet: every 0.x version is a pre-release, 1.0 will be the first release. The current version is in `VERSION`; projects record theirs in `board.json` → `generator_version`.

## 0.4.4

**One guard, written once.** The write and command rules now exist only in Python (`core/guard.py`). Before every write and every `bash` command inside a Polier project the plugin asks `tools/guard.py` and shows its answer. The JavaScript copies of the scope, policy and kill rules and their mirror tests are gone. A write the guard cannot decide is blocked with the reason; a command goes through and the stop check still sees what it wrote.

**One board schema.** The versions 0.9, 1.0, 1.1 and 1.2 are one schema. `schema_version` is optional and, if set, `"1.0"`. The unused task fields `labels`, `estimate_hours`, `planned_start` and `target` are gone. Without a `worktrees` setting, M and L default to `required`.

**One set of words.** The phases A to I are gone; `prompt/generator.md` is organised by the nine stations, and the cheatsheet, rubric, skill and catalog follow. `prompt/generator.md` shrank from about 7,900 to 3,500 words and `prompt/dsh.md` from about 3,900 to 1,900, without dropping a rule. Notes about older versions and references to an old design document are removed from code and docs.

**Adopting it.** A board with `schema_version` 1.1 or 1.2 sets it to `"1.0"` or removes it, and drops the four removed fields.

## 0.4.3

Version numbers reset; equals the former 4.3.0. Before 1.0, `feat`, `fix` and `perf` commits bump the third number and a breaking change the second, and every GitHub release is a pre-release.

## Before 0.4.3

The versions 0.4.0 to 4.3.0 were development steps toward the current shape: a prompt generator that became a DeepSeek Harness plugin, the board with gates and evidence, claims, slots and worktrees, `policy.json` with approvals and run records, the factory line with its catalog, specialist roles, Magic UI for web front ends and automatic versions. Their detailed notes are in the git history.
