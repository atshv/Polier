# Polier planning record

`board.json` is the Polier repository's own planning board (schema 1.0): six
stages, task IDs `PL-01` … `PL-25`, dependencies as in the work plans.
`STATUS.md` is generated from it with `python3 tools/render_status.py plans`.

- **Stages 1–5, 1.0** (`PL-01` … `PL-17`): board schema 1.0, runtime slots,
  exclusive gates, claims, worktrees, profile L, contracts, release and smoke
  gates, brief quality and drift detection. `PL-17` stays in `review` until the
  owner approves the 1.0.0 release (open question Q1).
- **Stage 6, 1.1** (`PL-18` … `PL-25`): the orchestration control plane —
  policy-as-code, run records with attempts, the state machine and its
  checkpoints, approvals, the dispatch plan, audit/check/status integration,
  adapter enforcement and the process/documentation update. The design contract
  is [`1.1-design.md`](1.1-design.md); each task was implemented in one
  branch-sized change set and committed as `PL-xx: <title>`.

The gates for a task are `npm test`, `python3 tools/check.py
examples/minimal-cli`, `python3 tools/check.py examples/monorepo-mini` and the
task's own tests.

Nothing in this folder ships with the package; it is the traceable plan, not a
generated project. Do not run `tools/check.py` on it (it is not a scaffolded
project, and `plans/STATUS.md` intentionally shows the plan of the package
itself).
