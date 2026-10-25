# packages/engine

## Commands

- **Configure/build:** `cmake -S packages/engine -B packages/engine/build && cmake --build packages/engine/build` → library `canvas_engine`.
- **Tests:** `ctest --test-dir packages/engine/build --output-on-failure` → all green.
- **WASM:** `emcmake cmake -S packages/engine -B packages/engine/build-wasm && cmake --build packages/engine/build-wasm` → `canvas_engine_wasm.wasm`.

## Deviations from the root `AGENTS.md`

- CMake only; there is no npm script in this package.
- `build/` and `build-wasm/` are gitignored build folders; never commit them.
- `src/wasm_bindings.cpp` changes only in the task that owns the WASM export list (`ENG-02`).

## Pitfalls

- Configure into a fresh build folder when `CMakeLists.txt` changed; a stale cache hides new targets.
- Guard Emscripten-only code with `#ifdef __EMSCRIPTEN__`; the native unit build must keep working.
- The C API uses only primitive types and `extern "C"`; a C++ type in the signature breaks the JS binding.
