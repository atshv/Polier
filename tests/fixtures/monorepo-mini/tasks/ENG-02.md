# ENG-02 — WASM bindings and size budget

## Goal

The engine builds to a browser-loadable WebAssembly module within the documented size budget.

**Why:** The web app loads the engine as WASM. The engine-spike exit decision needs a measured size and a stable export list before the owner records continue or stop.

**Satisfies:** D3

## Scope

- the C export list in `src/wasm_bindings.cpp`: contract version, node count, hit test
- the TypeScript declarations in `types/index.d.ts` that `apps/web` and `packages/ui-kit` import
- the Emscripten target in `CMakeLists.txt` and the `build-wasm/` output
- `tools/size_check.py`, the size gate inside the package

## Out of scope

- new engine features; the geometry is frozen by ENG-01
- the JSON decoder in the browser app (WEB-02)
- hosting the `.wasm` file; the app serves it from its own build
- a size optimisation pass beyond the 250 kB budget

## Acceptance

A1 WHEN `emcmake cmake -S packages/engine -B packages/engine/build-wasm` and the build run, THEN the system SHALL write `canvas_engine_wasm.wasm` and `canvas_engine_wasm.js` under `packages/engine/build-wasm/` and exit 0.

A2 WHEN a Node harness loads the module, THEN the system SHALL expose `canvas_contract_version_major()` returning `1`, and the declarations in `types/index.d.ts` SHALL describe exactly the exported functions.

A3 WHEN `python3 packages/engine/tools/size_check.py` runs, THEN the system SHALL measure the raw `.wasm` size and exit 0 only while it is at most 250 kB; above the budget it SHALL exit 1 with the measured value.

## Context pack

**Read exactly:**

- `packages/engine/ARCHITECTURE.md` (P-2 and the output list)
- `packages/engine/include/engine/canvas.h` (the C++ surface to wrap)
- `packages/engine/src/wasm_bindings.cpp` (current exports)
- `packages/engine/CMakeLists.txt` (the `EMSCRIPTEN` block)
- `packages/engine/types/index.d.ts`
- `docs/gates/wasm-emscripten.md` (gate commands and pitfalls)
- `docs/quality.md` (the `wasm-size` row)

**Do not read:** the sync service, the app sources, other briefs.

**Budget:** ≤ 15,000 tokens input.

## Specifications

- **Package:** `packages/engine` — this task writes only inside the package.
- **Exports:** `extern "C"` only, primitive types only (P-2): `canvas_contract_version_major()`, `canvas_node_count(const Canvas*)`, `canvas_hit_test(const Canvas*, double, double, uint64_t*)`.
- **Memory:** the module is loaded and used from the app's main thread in 1.0; no threads, no pthreads link flags.
- **Artifact names:** target `canvas_engine_wasm`, output `canvas_engine_wasm.wasm` plus `canvas_engine_wasm.js`; they stay in `build-wasm/` and are gitignored.
- **TypeScript declarations:** `CanvasHandle` with `nodeCount()`, `hitTest(x, y)` and `contractVersion()`, matching the exports one to one.
- **Size gate:** `tools/size_check.py` reads the `.wasm` path from a constant, measures with `Path.stat()`, prints `size <bytes> / budget 256000`, and compares against 250 kB (250,000 bytes). Standard library only.
- **Changed files:** `src/wasm_bindings.cpp`, `types/index.d.ts`, `CMakeLists.txt`; new file `tools/size_check.py`.
- **Reference:** `packages/engine/ARCHITECTURE.md` for the export rule.

## Pitfalls

- Emscripten flag names change between versions; take them from the pinned 3.1.61 docs in `docs/versions.md`, never from a blog [VERIFY: exact link flags for 3.1.61].
- `file://` loading fails for WASM; test through the app or a local HTTP server, never by opening the file.
- `EXPORTED_FUNCTIONS` needs the leading underscore in Emscripten naming; a typo yields a silent missing function, not a build error.
- The size budget counts the raw `.wasm`, not the gzip transfer size; do not compare the wrong number.
- Do not commit `build-wasm/`; the artifact is reproducible.

## Edge cases

- Empty document: `canvas_node_count(nullptr)` returns `0` and must not crash.
- `hit_test` with no hit: returns `0` and leaves the out-parameter untouched.
- A release build (`-O3`) is smaller than the debug build; measure the build the app loads and record which one in the gate log.
- A size of exactly 250,000 bytes passes; 250,001 fails.

## Gates

1. `emcmake cmake -S packages/engine -B packages/engine/build-wasm` → exit 0, "Configuring done".
2. `cmake --build packages/engine/build-wasm --parallel` → exit 0, `.wasm` and `.js` written.
3. `node packages/engine/build-wasm/canvas_engine_wasm.js` → exit 0, exports answer.
4. `python3 packages/engine/tools/size_check.py` → exit 0, size within 250 kB.
5. `python3 .generator/tools/boundaries.py .` → exit 0, no cross-package import.

A gate passes when command, exit code and expected output match; the output is the evidence. If a gate fails: read the cause, fix the code, rerun the gate.

## Limits

- **Scope:** only `packages/engine/src/wasm_bindings.cpp`, `packages/engine/types/index.d.ts`, `packages/engine/CMakeLists.txt`, `packages/engine/tools/size_check.py` — geometry files are forbidden
- **Stop:** max. 2 rework rounds; if the size budget is exceeded after one optimisation round, stop and report the number for the stage decision
- No new dependencies; no flags without a pinned source

## Output (YAML, no prose)

```yaml
task_id: ENG-02
status: submitted   # submitted | blocked | failed
changed_files: []
evidence: []        # [{gate, command, exit_code, output_tail}]
acceptance: []      # [{id, passed, how}]
open_questions: []
```
