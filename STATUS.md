# Status

**Project:** polier-next · **Profile:** S · **Stage:** 1 of 1

> Generated from `board.json`. Do not edit by hand.

Factory line (✓ closed, bold = current station): idea ✓ · concept ✓ · design ✓ · architecture ✓ · plan ✓ · **build (3/5 checklist items)** · verify · release · operate

## Ready now

- `M02` Eval runner and workflow
  - M01: evals/ holds 8 process cases; run them with the flags in docs/gates/node.md (--mocks off, Polier MCP grant, Write Edit, --scaffold).
  - M01: Write/Edit attempt graders are with-only: a guard-denied attempt still counts as a call; score outcomes on file contents.
  - M01: Pass --output-dir outside the repo: results under evals/ sit inside the plugin's skills path '.'.

## Orchestration

- Limits: 3 attempts/task, 1 in progress
- Next wave: none — nothing is ready
- Running: `M10` attempt 1/3
- Blocked: M02 (missing brief); M07, M08, M09, M11 (open dependency)
- Approvals pending: none

## Done

- [x] `M01` Process eval suite — status: `done` — owner: —
- [x] `M03` Retro over project records — status: `done` — owner: —
- [x] `M04` Quick track rule and command — status: `done` — owner: —
- [x] `M05` pl_quick tool — status: `done` — owner: —
- [x] `M06` Change proposals core — status: `done` — owner: —

## In progress

- [ ] `M10` Lock the scope under review; lead-only quick and change commands — status: `in_progress` — owner: —

## Blocked / failed

- none

## Open

- [ ] `M02` Eval runner and workflow — status: `pending` — owner: —
- [ ] `M07` pl_change tool and lint finding — status: `pending` — owner: —
- [ ] `M08` Process docs for the new tracks — status: `pending` — owner: —
- [ ] `M09` Security review of the first stage — status: `pending` — owner: —
- [ ] `M11` Owner decisions when no dialog appears — status: `pending` — owner: —

## Decisions

- 2026-11-12 `ADR-0001` Process evals with claude plugin eval against the real plugin (`docs/adr/ADR-0001-process-evals.md`)
- 2026-11-12 `ADR-0002` The retro reads project records read-only (`docs/adr/ADR-0002-retro-read-only.md`)
- 2026-11-12 `ADR-0003` Change proposals as approved deltas (`docs/adr/ADR-0003-change-proposals.md`)
- 2026-11-12 `ADR-0004` The quick track is an ordinary task (`docs/adr/ADR-0004-quick-track.md`)

## Open questions

- `Q2` Tasks of an approved change proposal cannot name its new D-items (D5–D8) on the board until the proposal is applied, which happens only after its tasks are done. Should check.py accept D-items of approved, unapplied proposals (M07)? — blocks: M07 — status: `open`
