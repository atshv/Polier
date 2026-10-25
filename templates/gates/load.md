# Gate Catalogue: Load

> Copy the gates the project has to `docs/gates/load.md`; delete the rest. Replace every `<...>`; the tool and thresholds come from the project docs.

| Gate | Command shape | Expected |
| --- | --- | --- |
| `load` | `k6 run <script>` or the project's load command [VERIFY: from manifest/docs] | exit 0, thresholds pass |
| `load-smoke` | a short run, e.g. 1 VU for 30 s [VERIFY: from project docs] | exit 0, no errors |

- Thresholds are documented before the run (p95 latency, error rate, throughput); the gate fails when one misses.
- Load tests are `"exclusive"`: they perturb a shared service. Never run them against production, staging or another session's server.
- Run against the slot's local server unless the owner approved another target.

## Pitfalls

- Results are not comparable across machines and networks; record the environment and commit the result summary.
- A cold start, an empty cache or a database without data distorts the result; warm up first and seed the same data.
- CI timeouts kill long runs; keep the script short enough for the pipeline or run it manually with approval.
- A load run that leaves processes or data behind breaks the next test; stop the server you started and reset the slot database.
- Never use a load test to "prove" readiness on production data without the owner's approval.
