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
| `docs/` | module map, quality, versions, environments, releasing, design rules, ADRs |
| `tools/` | project gates: `layout_check.py`, `contract_check.py` |
| `tasks/` | task briefs (just in time) |
| `reviews/evidence/` | gate records and logs |

## Documentation

- [Architecture](ARCHITECTURE.md)
- [Agent rules](AGENTS.md)
- [Status](STATUS.md)
- [Module structure](docs/module-map.md)
- [Quality and gates](docs/quality.md)
- [Dependency versions](docs/versions.md)
- [Environments](docs/environments.md)
- [Releasing](docs/releasing.md)
- [State contract](contracts/state/README.md)
