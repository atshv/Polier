# Gate Catalogue: WebAssembly / Emscripten

> Gates of `packages/engine` under Emscripten. Flags change between Emscripten versions — verify them against the pinned docs in `docs/versions.md`.

| Gate | Command shape | Expected |
|---|---|---|
| `wasm-build` | `emcmake cmake -S packages/engine -B packages/engine/build-wasm` then `cmake --build packages/engine/build-wasm` [VERIFY: from the Emscripten docs] | exit 0, `canvas_engine_wasm.wasm` and `canvas_engine_wasm.js` written |
| `wasm-test` | `node packages/engine/build-wasm/canvas_engine_wasm.js` [VERIFY: harness file from the build] | exit 0, exported functions answer |
| `wasm-size` | `python3 packages/engine/tools/size_check.py` [VERIFY: budget from `docs/quality.md`] | exit 0, size within the budget |
| `wasm-serve` | the app dev server on the slot port | serves without console errors |

- The size budget is 250 kB raw for the 1.0 spike; `ENG-02` measures it and records the number in the gate log.
- `emsdk` activation (`emsdk activate 3.1.61`) and the version come from `docs/versions.md`; never use `latest`.
- Export and memory flags belong in `CMakeLists.txt`, not copied from a blog [VERIFY: from the pinned Emscripten docs].

## Pitfalls

- Emscripten changes flag names and defaults between versions; an old command can silently produce a broken module.
- `file://` loading fails for WASM: serve over HTTP and test in the browser test, not by opening the file.
- Node and browser builds differ; run the harness the project ships.
- Size assertions belong in `wasm-size`, not in the unit tests; never assert on debug builds.
- Never commit `build-wasm/`; it is reproducible from `CMakeLists.txt`.
- The engine is imported by the app; run the `boundaries` gate too.
