# Gate Catalogue: WebAssembly / Emscripten

> Copy the gates the project has to `docs/gates/wasm-emscripten.md`; delete the rest. Replace every `<...>`; flags change between Emscripten versions — verify them against the pinned docs.

| Gate | Command shape | Expected |
| --- | --- | --- |
| `wasm-build` | `emcmake cmake -S . -B build-wasm` then `cmake --build build-wasm` [VERIFY: from manifest/docs] | exit 0, `.wasm` and `.js` artifacts written |
| `wasm-test` | `node <test harness>` [VERIFY: from manifest/docs] | exit 0, all tests pass |
| `wasm-size` | `du -b build-wasm/<artifact>.wasm` against the budget [VERIFY: budget from docs] | within the documented size budget |
| `wasm-serve` | the project dev server on the slot's port [VERIFY: from manifest/docs] | serves without console errors |

- `emsdk` version and activation (`emsdk activate <version>`) come from `docs/versions.md`; never `latest`.
- Export, memory and modularisation flags belong in `CMakeLists.txt` or the toolchain file, not copied from a blog [VERIFY: from pinned docs].

## Pitfalls

- Emscripten changes flag names and defaults between versions; an old command can silently produce a broken module.
- `file://` loading fails for WASM: serve over HTTP and test in the browser test, not by opening the file.
- Node and browser builds differ; run the test harness the project ships.
- Size and memory-growth flags are easy to inflate; keep assertions off in release builds [VERIFY: from docs].
- Never commit `build-wasm/`; it is reproducible from the manifest.
- A WASM package is usually imported by an app: run the `boundaries` gate too (`node-ts.md`).
