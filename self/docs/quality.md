# Quality: Polier next

> Station 2 (concept), **draft**. Done scenarios D1..Dn (`CON-04`); every MVP story maps to one.

| ID | Scenario | Stories |
| --- | --- | --- |
| D1 | The eval suite runs in CI with `--ablation with-without`; Polier beats the baseline on every process case, and a deliberately broken guard turns at least one case red. | US1 |
| D2 | `tools/retro.py` on both reference fixtures and one real project writes `docs/retro.md` with at least one error class that names a Polier file, and changes nothing in the projects. | US2 |
| D3 | On `tests/fixtures/minimal-cli`, a change proposal adds a feature: owner approval recorded, linked task done, delta merged into concept and quality, `check.py` green. | US3 |
| D4 | On the same fixture, a quick fix runs as one task with gate records and a passing review; a quick request that adds a trait is refused with the proposal path. | US4 |
