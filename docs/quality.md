# Quality: Polier next

> Station 2 (concept) wrote the definition of done; station 5 (plan) traces it. Every D-item is named in at least one task's `satisfies` on the board.

## Definition of done

- **D1** The eval suite runs in CI with `--ablation with-without`; Polier beats the baseline on every process case, and a deliberately broken guard turns at least one case red. (US1)
- **D2** `tools/retro.py` on both reference fixtures and one real project writes a report with at least one error class that names a Polier file, and changes nothing in the projects. (US2)
- **D3** On `tests/fixtures/minimal-cli`, a change proposal adds a feature: owner approval recorded, linked task done, delta merged into concept and quality, `check.py` green. (US3)
- **D4** On the same fixture, a quick fix runs as one task with gate records and a passing review; a quick request that adds a trait is refused with the proposal path. (US4)

## Trace

| D-item | Task (`satisfies`) | Acceptance | Gate |
| --- | --- | --- | --- |
| D1 | M01, M02, M09 | M01 A1–A5, M02 A1–A4, M09 A3 | evals-smoke, validate, line, audit |
| D2 | M03 | A1–A5 | tests, fixtures |
| D3 | M06, M07, M08, M09 | M06 A1–A6, M07 A1–A4, M09 A2 | tests, fixtures, line, audit |
| D4 | M04, M05, M08, M09 | M04 A1–A5, M05 A1–A3, M09 A1 | tests, fixtures, validate, audit |

D1's full two-arm run is the release gate of the stage (`npm run evals`, M02), not a per-task gate: it costs one suite run.

## Gates

The commands are in `docs/gates/python.md`, `docs/gates/node.md` and `AGENTS.md`; `pl_gate` records each run under `reviews/evidence/`.
