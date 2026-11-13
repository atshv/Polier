# Status

**Project:** polier-next · **Profile:** S · **Stage:** 1 of 1

> Generated from `board.json`. Do not edit by hand.

Factory line (✓ closed, bold = current station): idea ✓ · concept ✓ · design ✓ · architecture ✓ · plan ✓ · **build (1/5 checklist items)** · verify · release · operate

## Ready now

- `M03` Retro over project records
- `M04` Quick track rule and command
- `M06` Change proposals core

## Orchestration

- Limits: 3 attempts/task, 1 in progress
- Next wave: `M03` (tasks/M03.md)
- Running: `M01` attempt 2/3
- Blocked: M02, M05, M07, M08, M09 (open dependency)
- Approvals pending: none

## Done

- none

## In progress

- [ ] `M01` Process eval suite — status: `review` — owner: —

## Blocked / failed

- none

## Open

- [ ] `M02` Eval runner and workflow — status: `pending` — owner: —
- [ ] `M03` Retro over project records — status: `pending` — owner: —
- [ ] `M04` Quick track rule and command — status: `pending` — owner: —
- [ ] `M05` pl_quick tool — status: `pending` — owner: —
- [ ] `M06` Change proposals core — status: `pending` — owner: —
- [ ] `M07` pl_change tool and lint finding — status: `pending` — owner: —
- [ ] `M08` Process docs for the new tracks — status: `pending` — owner: —
- [ ] `M09` Security review of the first stage — status: `pending` — owner: —

## Decisions

- 2026-11-12 `ADR-0001` Process evals with claude plugin eval against the real plugin (`docs/adr/ADR-0001-process-evals.md`)
- 2026-11-12 `ADR-0002` The retro reads project records read-only (`docs/adr/ADR-0002-retro-read-only.md`)
- 2026-11-12 `ADR-0003` Change proposals as approved deltas (`docs/adr/ADR-0003-change-proposals.md`)
- 2026-11-12 `ADR-0004` The quick track is an ordinary task (`docs/adr/ADR-0004-quick-track.md`)

## Open questions

- `Q1` Which agent and judge model IDs does the eval workflow pin, and which Anthropic terms apply to the CI account? — blocks: M02 — status: `open`
