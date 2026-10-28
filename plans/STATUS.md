# Status

**Project:** polier · **Profile:** M · **Stage:** 6 of 6 (6 defined)

> Generated from `board.json`. Do not edit by hand.

## Stages

### Stage 1 — `incident-fixes` incident fixes

- State: complete
- Owner decision: `continue`
- Exit criteria: slots, exclusive gates, claims and worktree enforcement tested; 0.9 projects unchanged
- Tasks: PL-01, PL-02, PL-03, PL-04, PL-05, PL-16

### Stage 2 — `scale-to-l` scale to L

- State: complete
- Owner decision: `continue`
- Exit criteria: examples/monorepo-mini passes check.py; boundaries gate available
- Tasks: PL-06, PL-07, PL-08, PL-09

### Stage 3 — `release-contracts` release and contracts

- State: complete
- Owner decision: `continue`
- Exit criteria: release_check.py + smoke.py + contracts.py tested
- Tasks: PL-10, PL-11, PL-12

### Stage 4 — `brief-quality` quality of briefs

- State: complete
- Owner decision: `continue`
- Exit criteria: gate catalogue and templates complete
- Tasks: PL-13, PL-14, PL-15

### Stage 5 — `ship-1-0` ship 1.0

- State: tasks open
- Owner decision: `continue`
- Exit criteria: VERSION, CHANGELOG and both examples green in CI
- Tasks: PL-17
- Tasks open: PL-17

### Stage 6 — `orchestration` orchestration control plane

- State: complete
- Owner decision: `continue`
- Exit criteria: policy.json, runs/, reviews/approvals/ are the new state and are checked; state changes go through state.py; a done task needs the full evidence chain; dispatch.py turns the board into waves and names blocked tasks; adapters enforce policy; 0.9/1.0 projects are unchanged without policy.json
- Tasks: PL-18, PL-19, PL-20, PL-21, PL-22, PL-23, PL-24, PL-25

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
- [x] `PL-18` Policy as code — status: `done` — owner: —
- [x] `PL-19` Run records and attempts — status: `done` — owner: —
- [x] `PL-20` State machine and checkpoints — status: `done` — owner: —
- [x] `PL-21` Approvals with records — status: `done` — owner: —
- [x] `PL-22` Dispatch plan — status: `done` — owner: —
- [x] `PL-23` Audit, checks and status — status: `done` — owner: —
- [x] `PL-24` Adapter enforcement — status: `done` — owner: —
- [x] `PL-25` Process, templates and examples — status: `done` — owner: —

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
