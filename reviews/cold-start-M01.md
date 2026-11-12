# Cold start: M01

> `prompt/rubric.md` §4. A fresh headless Claude Code session (`claude -p`, Read and Glob only, no other tool) in an empty folder with only `ARCHITECTURE.md`, `AGENTS.md`, `STATUS.md` and `tasks/M01.md`. Date 2026-11-12.

## Round 1

**Result:** no blocking question; goal, scope, layer, gates and next checkpoint correct.

**Findings, closed before round 2:**

- Expected outcome given for only two of the eight cases → M01 got a table with fixture state, owner sentence and scored outcome per case.
- `evals-smoke` command only by reference → written into the brief's gates, with "no exclusive resource".
- Approval kind for protected paths not named → `AGENTS.md` names `protected_path`.
- `pl_state` arguments not stated → `AGENTS.md` names task and status.

## Round 2 — pass

No blocking question. Correct: goal, M01 scope and exclusions, files to change and to leave alone, layer (`evals/`, black box), gates (`check`, `validate`, `evals-smoke`, no exclusive resource), `pl_state` (`M01`, `in_progress`), `new_dependency` for `package.json`, `protected_path` (lead only) for protected paths.

Still named as missing, all listed in the brief's context pack and read when the task starts: the `case.yaml` and grader schema (`docs/research/claude-plugin-eval.md`, plugin-evals docs), fixture shape, ADR-0001, `docs/module-map.md`.

## Answer of round 2

Note: `STATUS.md` says this repo is **profile S**, so there are no package-level `ARCHITECTURE.md`/`AGENTS.md` to read.

1. **Goal:** Polier next adds four features to Polier: process evals, a retro over project records, change proposals for a shipped product, and a quick track for small changes. All four run locally and use only the standard library (ARCHITECTURE §1–2).

2. **M01 scope:** Eight process eval cases under `evals/`, one folder per case:
   - `close-open-station`, `close-complete-station`, `out-of-scope-write`, `chat-yes-dependency`, `record-a-gate`, `done-without-evidence`, `reviewer-fixes-code`, `hand-edit-board`.
   - Each folder holds `prompt.md`, `case.yaml` (`context.scaffold_script: fixture.sh`), `fixture.sh` and `graders/`.
   - Scored graders check outcomes only, so the no-plugin baseline could also pass them. Any grader on a `pl_*` tool call is `arm: with-only`.
   - `.gitignore` gets one line: `evals/results/`.

   **Explicitly out:** the `npm run evals` script and the CI workflow (both M02), and cases for retro, change proposals and the quick track (a later stage).

3. **Files:**
   - **Change:** new `evals/<case>/{prompt.md,case.yaml,fixture.sh,graders/*.md}` and the one line in `.gitignore`.
   - **Don't touch:** everything else. That includes `core/`, `tools/`, `plugin/`, `claude/`, `package.json`, `board.json`, `factory.json`, `policy.json`, `runs/`, `reviews/approvals/`, `VERSION`, `CHANGELOG.md` and `STATUS.md` (it's generated).

4. **Commands:**
   - First `pl_role` and `pl_task M01`.
   - Then the gates:
     - `npm run check` → `OK: …`
     - `claude plugin validate . --strict` → `Validation passed`
     - the `evals-smoke` command from the brief (`claude plugin eval . --case close-open-station --runs 1 … --max-cost-usd 2`) → exit 0, case score 1.0
   - Record the gates with `pl_gate`.
   - Before reporting, `pl_scope_check` should show only `evals/` and `.gitignore`, and `git status` should show the same.

5. **Missing for a plan:**
   - The exact `case.yaml` and grader schema.
   - The shape of `factory.json`, `board.json` and `policy.json` for the fixtures.
   - How the existing tests scaffold a project.
   - What ADR-0001 says about the cost cap.
   - The module map.
   - The gate names as written in `board.json` and their commands in `docs/gates/`. I haven't checked these: only the brief names `evals-smoke`.

6. **Extra file I'd need first:** `docs/research/claude-plugin-eval.md`, for the case and grader format. Close behind it are `tests/fixtures/minimal-cli/board.json` and `claude/test/claude.test.mjs`, which the context pack also lists.

7. **Layer:** the black-box suite, `evals/`. It drives the installed plugin only from outside and imports no module (ARCHITECTURE §3, AD-1).

8. **Proving gate:** `evals-smoke`, backed by `npm run check` and `validate --strict`. It needs **no exclusive resource**. It does call Anthropic's API with the maintainer's credentials, capped at 2 USD per run and 10 USD in total.

9. **Status and approvals:**
   - **`in_progress`:** the lead sets it with `pl_state` (task `M01`, status `in_progress`).
   - **New dependency:** any change to `package.json` needs a `new_dependency` approval.
   - **Protected path:** `policy.json`, `VERSION`, `CHANGELOG.md` and the release workflow need a `protected_path` approval, lead only.
   - Both go through `pl_approval`, never a "yes" in chat.
