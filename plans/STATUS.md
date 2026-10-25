# Status

**Project:** polier · **Profile:** M · **Stage:** 5 of 5 (5 defined)

> Generated from `board.json`. Do not edit by hand.

## Stages

### Stage 1 — `incident-fixes` Stage 1 — incident fixes

- State: complete
- Owner decision: `continue`
- Exit criteria: slots, exclusive gates, claims and worktree enforcement tested; 0.9 projects unchanged
- Tasks: PL-01, PL-02, PL-03, PL-04, PL-05, PL-16

### Stage 2 — `scale-to-l` Stage 2 — scale to L

- State: complete
- Owner decision: `continue`
- Exit criteria: examples/monorepo-mini passes check.py; boundaries gate available
- Tasks: PL-06, PL-07, PL-08, PL-09

### Stage 3 — `release-contracts` Stage 3 — release and contracts

- State: complete
- Owner decision: `continue`
- Exit criteria: release_check.py + smoke.py + contracts.py tested
- Tasks: PL-10, PL-11, PL-12

### Stage 4 — `brief-quality` Stage 4 — quality of briefs

- State: complete
- Owner decision: `continue`
- Exit criteria: gate catalogue and templates complete
- Tasks: PL-13, PL-14, PL-15

### Stage 5 — `ship-1-0` Stage 5 — ship 1.0

- State: complete
- Owner decision: `continue`
- Exit criteria: VERSION, CHANGELOG and both examples green in CI
- Tasks: PL-17

## Ready now

- none

## Done

- [x] `PL-01` Board schema 1.0 — status: `done` — owner: —
- [x] `PL-02` Runtime slots per worktree — status: `done` — owner: —
- [x] `PL-03` Exclusive gates and infra failures — status: `done` — owner: —
- [x] `PL-04` Cross-harness task claims — status: `done` — owner: —
- [x] `PL-05` Worktree enforcement, foreign changes — status: `done` — owner: —
- [x] `PL-06` Monorepo layout and package files — status: `done` — owner: —
- [x] `PL-07` Import boundaries between packages — status: `done` — owner: —
- [x] `PL-08` Stage exit gates and stop points — status: `done` — owner: —
- [x] `PL-09` Profile-dependent size budgets — status: `done` — owner: —
- [x] `PL-10` Release and environment templates — status: `done` — owner: —
- [x] `PL-11` Post-deploy smoke gate — status: `done` — owner: —
- [x] `PL-12` Machine-readable contracts — status: `done` — owner: —
- [x] `PL-13` Gate catalogue and versions.md — status: `done` — owner: —
- [x] `PL-14` UI brief fields and design rules — status: `done` — owner: —
- [x] `PL-15` Generator drift detection — status: `done` — owner: —
- [x] `PL-16` Guard extras — status: `done` — owner: —

## In progress

- [ ] `PL-17` Release 1.0 — status: `review` — owner: —

## Blocked / failed

- none

## Open

- none

## Decisions

- none on the board; details in `docs/adr/`.

## Open questions

- `Q1` Owner approval of the 1.0.0 CHANGELOG and the release commit is still open (PL-17 A3). — blocks: PL-17 — status: `open`
