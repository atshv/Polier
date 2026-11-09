# Quality: <Project name>

> Station 2 (concept) writes the definition of done; station 5 (plan) checks the trace. Every D-item is named in at least one task's `satisfies` on the board, and `tools/check.py` fails when one is not.

## Definition of done

- **D1** <an end-to-end scenario that must work at launch, observable by the owner>
- **D2** <...>
- **D3** <...>

## Trace

| D-item | Task (`satisfies`) | Acceptance | Gate |
| --- | --- | --- | --- |
| D1 | <M03> | <A1, A2> | <tests, e2e> |

## Gates

The commands are in `docs/gates/<stack>.md` and `AGENTS.md`; `pl_gate` records each run under `reviews/evidence/`.
