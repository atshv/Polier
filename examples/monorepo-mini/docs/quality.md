# Quality: canvas-mini

## Definition of done (project)

- **D1** Workspace and package map: the four packages on the board exist, each has an `ARCHITECTURE.md`, and `docs/module-map.md` lists every package path.
- **D2** State contract: version 1.0.0 is a JSON Schema 2020-12 with one valid and one invalid fixture; the engine, UI kit, service and app consume the same version.
- **D3** Engine: the C++ unit tests are green and the WebAssembly module builds within its documented size budget.
- **D4** End to end: the web app renders the shared document state from the engine and the UI kit and stays in sync through the service on the slot ports.
- **D5** Release: every environment has a smoke URL, the smoke gate passes after deployment, and the release check passes on a tag of `main`.

## Gates

| Gate | Command | Expected |
|---|---|---|
| `layout` | `python3 tools/layout_check.py` | exit 0, board, folders and contract files agree |
| `contracts` | `python3 tools/contract_check.py` | exit 0, version, fixtures and dependants agree |
| `configure` | `cmake -S packages/engine -B packages/engine/build` | exit 0, "Configuring done" |
| `build` | `cmake --build packages/engine/build` | exit 0, library target built |
| `cpp-unit` | `ctest --test-dir packages/engine/build --output-on-failure` | exit 0, all tests pass |
| `wasm-build` | `emcmake cmake -S packages/engine -B packages/engine/build-wasm && cmake --build packages/engine/build-wasm` | exit 0, `.wasm` and `.js` written |
| `wasm-test` | `node packages/engine/build-wasm/canvas_engine_wasm.js` | exit 0, exported functions answer |
| `wasm-size` | `python3 packages/engine/tools/size_check.py` | exit 0, size within budget |
| `types` | `npm run typecheck` in the package | exit 0, no type errors |
| `tests` | `npm test` in the package | exit 0, all tests pass |
| `lint` | `npm run lint` in the package [VERIFY: lint script lands with the first test task] | exit 0, no lint errors |
| `boundaries` | `python3 .generator/tools/boundaries.py .` | exit 0, no cross-package import |
| `visual-diff` | `npx playwright test --grep @visual` in `apps/web` | exit 0, screenshots within tolerance |
| `e2e` | `npx playwright test` in `apps/web` | exit 0, full flow green (exclusive) |
| `smoke` | `python3 .generator/tools/smoke.py --url <environment-url> --expect-status 200 --path /` | exit 0, `SMOKE OK` |
| `release` | `python3 .generator/tools/release_check.py --allow-untagged` | exit 0, clean tree and released stages |

A gate passes when command, exit code and expected output match; the output is the evidence. The task passes when all gates are green, every acceptance criterion is evidenced and the reviewer gives `pass` with no blockers. Command shapes per stack: `docs/gates/`.

## Review

- The reviewer is not the author; the reviewer sees diff, acceptance criteria and gate records, not the author's reasoning.
- Every finding: `severity`, `file`, `line`, `criterion`, `issue`, `evidence`, `fix_hint`; results go to `reviews/<ID>.md`.
- No style questions unless they cause defects; at most five findings per round.
- The reviewer checks `docs/design-rules.md` for every UI path; a brief value that is not a token there is a finding.

## Human checklist per task

- [ ] Gates actually run and output seen.
- [ ] Acceptance A1..An evidenced individually.
- [ ] Diff only within the task scope; contract paths only when `contracts/` changed.
- [ ] No tests changed without approval.
- [ ] No placeholders or TODOs.
- [ ] `STATUS.md` regenerated from the board.
- [ ] Commit `<ID>: <title>`.

## Deliberately not checked (1.0)

- Offline behaviour and conflict resolution.
- Performance beyond 4,000 nodes per document.
- Mobile layouts and touch gestures.
- Cross-browser support beyond current Chromium.
