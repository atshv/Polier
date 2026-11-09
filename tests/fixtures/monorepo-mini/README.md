# canvas-mini

A collaborative canvas editor in four parts: a C++ scene core compiled to WebAssembly, a TypeScript UI kit, a Node sync service and a Next.js app. `board.json` is the plan; `STATUS.md` is generated from it.

## Requirements

- Node.js 22 [VERIFY: from the project `.nvmrc`]
- CMake 3.28 and Emscripten 3.1.61 for the engine [VERIFY: from `docs/versions.md`]
- Python 3.12 for the Polier tooling in `.generator/`

## Quickstart

```bash
cmake -S packages/engine -B packages/engine/build
cmake --build packages/engine/build
ctest --test-dir packages/engine/build --output-on-failure

cd packages/ui-kit && npm ci && npm run typecheck
cd services/sync && npm ci && npm test
cd apps/web && npm ci && npm run dev
```

## Structure

| Path | Contents |
|---|---|
| `packages/engine/` | C++17 scene core, WASM bindings, CTest suite |
| `packages/ui-kit/` | React components, design tokens, component tests |
| `services/sync/` | HTTP/WebSocket sync service, contract validation |
| `apps/web/` | Next.js app shell, sync client, Playwright e2e |
| `contracts/state/` | Document-state schema and fixtures |
| `docs/` | module map, orchestration, quality, versions, environments, releasing, design rules, ADRs |
| `policy.json` | limits (attempts, tasks in progress, review rounds), protected paths, approvals, denied commands |
| `runs/` | one execution record per task: attempts and gate/review/state events |
| `reviews/approvals/` | human decisions on high-risk actions (`AP-NNN.json`) |
| `tools/` | project gates: `layout_check.py`, `contract_check.py` |
| `tasks/` | task briefs (just in time) |
| `reviews/evidence/` | gate records and logs |

## Orchestration

`board.json` is the plan, `runs/` is what happened, `policy.json` is the rules.
A task moves through `in_progress → verifying → review → done` only with
`tools/state.py`; `tools/dispatch.py` names the next wave, `tools/audit.py`
checks the evidence chain of a done task. The one-page model is
[docs/orchestration.md](docs/orchestration.md); the limits are in `policy.json`.
`AP-001` is a pending `new_dependency` approval for `API-01`.

## Documentation

- [Architecture](ARCHITECTURE.md)
- [Agent rules](AGENTS.md)
- [Orchestration](docs/orchestration.md)
- [Status](STATUS.md)
- [Module structure](docs/module-map.md)
- [Quality and gates](docs/quality.md)
- [Dependency versions](docs/versions.md)
- [Environments](docs/environments.md)
- [Releasing](docs/releasing.md)
- [State contract](contracts/state/README.md)
