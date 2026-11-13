# C02 — A learning loop and a memory across projects

**Status:** draft — waits for the owner's `scope_change` approval · **Asked by:** owner, 2026-11-13 · **Format:** ADR-0003 (written by hand; `tools/change.py` does not exist yet, M06) · **Builds on:** F1 evals (M01 done), F2 retro (M03), F3 change proposals (M06), F10 briefs (C01)

## Why

Polier gets better today only when someone happens to look. In this line three real defects surfaced because Polier worked on itself and was measured:

- `tools/check.py` linted every Markdown file under `node_modules/`, so any web project failed its lint after `npm install` (fixed in `164a467`).
- In Claude Code, an `MCP_TOOL_TIMEOUT` of 60 s cut `pl_gate` off before a test suite finished (fixed in `80852e2`).
- A session asked to act as reviewer, without reviewer mode and without a running task, may change the task's code (eval `reviewer-fixes-code`; task M10 proposed).

None of these would have been remembered in the next project, and nothing turned them into a lasting check except by hand. The owner wants Polier to become smarter actively.

## What

### F12 — The learning loop

1. **Measure:** at the end of every stage the lead runs the retro (F2) on the project; the stage cannot be marked complete without a retro report in `docs/retro/stage-<N>.md`.
2. **Name:** each error class with at least two examples becomes an entry in the idea backlog (F11) or, when it points at Polier itself, a draft change proposal against the Polier repository, with the records as evidence.
3. **Pin:** **every defect found in Polier becomes an eval case** before or with its fix. A fix commit without a new or changed case under `evals/` is a `tools/check.py` finding in the Polier repository (checked by `scripts/check.py`), unless the commit names why no case can show it.
4. **Prove:** a release of Polier runs the two-arm eval suite (`npm run evals`, M02); a case that got worse than at the last release blocks the release until the owner accepts it with a `release` approval.

### F13 — A memory across projects

- **Lessons file** `~/.polier/lessons.md` (location overridable with `POLIER_HOME`), written only through `tools/lessons.py add|list|match|retire`: each lesson has an ID, the pitfall in one sentence, where it bites (stack, tool, harness, file pattern), the fix, the source (project record, retro class, commit) and a date.
- **Use:** `tools/brief.py draft` (F10) and the gate templates pull the lessons that match the task's stack and scope into the brief's *Pitfalls* section with their IDs; `pl_preflight` shows lessons that match the project's harness and environment (e.g. "MCP_TOOL_TIMEOUT is set").
- **Feed:** the retro proposes lessons; the lead or the owner adds them; a lesson that has not matched for a year is offered for retirement.
- **Privacy:** local only, no telemetry, nothing leaves the machine; a lesson holds no secret, path outside the project or personal data (`tools/lessons.py add` refuses absolute home paths and common secret patterns). Sharing is an explicit export the owner runs.

## Deltas to the living docs

### `docs/concept.md#features` — ADDED

| F12 | **Learning loop**: retro at every stage end, error classes into ideas or proposals against Polier, every Polier defect pinned as an eval case, releases gated by the two-arm suite | MVP (stage 3) | Polier improves measurably, not by chance |
| F13 | **Memory across projects**: `~/.polier/lessons.md` through `tools/lessons.py`, matched into briefs and preflight | MVP (stage 3) | a pitfall found once is never paid for twice |

### `docs/concept.md#user-stories` — ADDED

- **US7** (F12) As the maintainer I want every defect pinned by an eval case and every release checked against the last one so that Polier never silently gets worse.
  - WHEN a commit fixes a Polier defect without a new or changed eval case and without a reason THEN `npm run check` names the commit.
  - WHEN the two-arm suite scores a case lower than at the last release THEN the release stops until a `release` approval accepts it.
- **US8** (F13) As the owner I want pitfalls from earlier projects in my briefs so that agents do not repeat them.
  - WHEN a task's stack or scope matches a lesson THEN its drafted brief lists the lesson with its ID under *Pitfalls*.
  - WHEN a lesson would contain a secret pattern or an absolute home path THEN `tools/lessons.py add` refuses it.

### `docs/quality.md#definition-of-done` — ADDED

- **D7** The three defects of this line are lessons and eval cases; a release run of Polier compares the suite with the previous release and stops on a worse case. (US7)
- **D8** On a fixture project with a Node stack, a drafted brief lists the `node_modules` lint lesson, and `pl_preflight` in an environment with `MCP_TOOL_TIMEOUT` set shows the timeout lesson. (US8)

## Proposed tasks (stage 3, after C01's stage 2)

| ID | Title | Role | Scope (main paths) |
| --- | --- | --- | --- |
| M16 | Lessons core and command | backend-builder | `core/lessons.py`, `tools/lessons.py`, tests |
| M17 | Lessons in briefs and preflight | backend-builder | `core/brief.py`, `core/preflight.py`, tests |
| M18 | Stage-end retro and retro-to-idea/proposal | backend-builder | `core/retro.py`, `tools/retro.py`, `core/state.py` (stage completion), tests |
| M19 | Eval pin rule and release comparison | backend-builder | `scripts/check.py`, `scripts/release.py`, `.github/workflows/release.yml` (protected: owner approval), tests |
| M20 | Process docs for the loop | architect | `prompt/generator.md`, `prompt/orchestration.md`, `AGENTS.md`, `SKILL.md` |
| M21 | Pin the three known defects | backend-builder | `evals/` (cases for the lint and timeout defects), lessons seed |

## Ideas for the backlog (F11), not part of C02

- Calibrate task size from records: complexity versus attempts and review rounds; propose splits.
- Pick the model per role from eval and run data instead of the fixed `fast | standard | strong` hint.
- Real token and cost figures per task (F7) to make budgets realistic.
- A cold start for every brief before its task starts; an adversarial critic in concept and architecture; a check that a grader can pass in the baseline arm.
- Remember the owner's decisions and rejected ideas so Polier does not ask twice.
- Automatic freshness sweep of `[VERIFY]` markers and dated sources (F6).

## Approval

`scope_change` for C02, recorded with `pl_approval` (or `tools/approve.py` without a dialog) before any task of C02 starts.
