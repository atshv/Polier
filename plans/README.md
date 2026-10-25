# Polier 1.0 planning record

`board.json` is the 1.0 upgrade board of the Polier repository itself (schema 1.0:
five stages, task IDs `PL-01` … `PL-17`, dependencies as in the work plan). `STATUS.md`
is generated from it with `python3 tools/render_status.py plans`.

The work plan this board implements was supplied by the owner
(`polier-1.0-workplan.md`, section 4). Each task was implemented in one branch-sized
change set and committed as `PL-xx: <title>`; the gates are `npm test`,
`python3 tools/check.py examples/minimal-cli` and the task's own tests. `PL-17` stays
in `review` until the owner approves the 1.0.0 release (open question Q1).

Nothing in this folder ships with the package; it is the traceable plan, not a
generated project. Do not run `tools/check.py` on it (it is not a scaffolded project).
