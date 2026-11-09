# Architecture: packages/engine

**As of:** 2026-10-17 · **Kind:** `package` · **Owner:** geometry owner

## Purpose

The scene core of canvas-mini: node model, geometry and hit testing, compiled to WebAssembly and loaded by `apps/web`. It knows no React, no HTTP and no storage. Not its job: rendering, transport, persistence, undo UI.

## Inputs

- Node operations from the app through the C API declared in `include/engine/canvas.h`.
- Document state decoded from the contract `contracts/state/state.schema.json` version 1.0.0 (decoder in `src/wasm_bindings.cpp`).

## Outputs

- Updated node arrays, hit-test results and document bounds as plain C structs.
- Build artifacts `canvas_engine_wasm.wasm` and `canvas_engine_wasm.js` under `build-wasm/` (never committed).

## Invariants

| ID | Rule | Prevents |
|---|---|---|
| P-1 | All geometry is double precision; no float shortcuts in the public API. | drift at high zoom, coordinate jumps |
| P-2 | The C API in `include/engine/canvas.h` is the only exported surface; no C++ type crosses it. | ABI breakage between engine and app |
| P-3 | Node width and height are never negative; invalid input is rejected, not clamped. | corrupt state, silent data loss |
| P-4 | Hit testing allocates nothing per call. | frame drops while dragging |

## Allowed imports

- `may_import` from `board.json`: none.
- Standard library and C++17 only; no include into another package.
- Gate: `boundaries` (see root `AGENTS.md`).

## Commands

- **Build:** `cmake -S packages/engine -B packages/engine/build && cmake --build packages/engine/build` → static library `canvas_engine`.
- **Tests:** `ctest --test-dir packages/engine/build --output-on-failure` → all green (added by `ENG-01`).
- **WASM:** `emcmake cmake -S packages/engine -B packages/engine/build-wasm && cmake --build packages/engine/build-wasm` → `.wasm` and `.js` written.

## Links

- Root: `../../ARCHITECTURE.md` (AD-1, AD-2, AD-4), `../../docs/module-map.md`
- Contract: `../../contracts/state/README.md`
- Gate catalogue: `../../docs/gates/cpp-cmake.md`, `../../docs/gates/wasm-emscripten.md`
