# ENG-01 — C++ scene core and unit tests

## Goal

The engine library exposes node operations with a passing CTest suite and a documented geometry API.

**Why:** ENG-02 only wraps this library for WebAssembly, and the stage exit decision needs green unit tests before the WASM size review.

**Satisfies:** D3

## Scope

- the node model and the document in `canvas.h` / `canvas.cpp`: insert, remove, resize, bounds, hit test
- the colour helper in `color.h` / `color.cpp`
- the CTest target: build registration in `CMakeLists.txt` and the test file `tests/engine_tests.cpp`
- the documented C API boundary: only primitive types cross it (P-2)

## Out of scope

- the WASM bindings and the export list (ENG-02)
- rendering, DOM, network, storage — the engine knows none of them
- a JSON decoder in the engine; the binding layer decodes later (ENG-02)
- performance tuning beyond the allocation rule P-4

## Acceptance

A1 WHEN `Canvas::insert_node` receives a node with non-negative `width` and `height`, THEN the system SHALL assign a fresh id, store the node and return the id, and `node_count()` SHALL grow by one.

A2 WHEN `insert_node` or `set_size` receives a negative width or height, THEN the system SHALL reject the input (return `0` or `false`) and leave the document unchanged (P-3).

A3 WHEN `hit_test(x, y, &id)` is called, THEN the system SHALL return the topmost node containing the point and `false` when no node contains it (P-4).

A4 WHEN `ctest --test-dir packages/engine/build --output-on-failure` runs, THEN the system SHALL report every CTest case green, including empty-document bounds, remove-missing-id and the 4,000-node case.

## Context pack

**Read exactly:**

- `packages/engine/ARCHITECTURE.md` (P-1 … P-4)
- `packages/engine/CMakeLists.txt` (current targets)
- `packages/engine/include/engine/canvas.h` (public API and structs)
- `packages/engine/include/engine/color.h`
- `packages/engine/src/canvas.cpp` (current implementation)
- `docs/gates/cpp-cmake.md` (gate commands and pitfalls)
- `contracts/state/state.schema.json` (`$defs/node` — the fields the node mirrors)

**Do not read:** other packages, the briefs of later tasks, `src/wasm_bindings.cpp`.

**Budget:** ≤ 15,000 tokens input.

## Specifications

- **Package:** `packages/engine` — this task writes only inside the package.
- **Language and API:** C++17, no exceptions across the C API boundary; the classes stay in `namespace canvas` (P-2).
- **Node fields:** `id`, `type`, `x`, `y`, `width`, `height`, `rotation`, `fill`; they mirror `$defs/node` of the contract with `id` as the internal number.
- **Geometry rules:** all coordinates are doubles (P-1); `document_bounds()` returns zeros for an empty document; `hit_test` iterates from the topmost node and allocates nothing (P-4).
- **IDs:** monotonically increasing from 1; a removed id is never reused.
- **Tests:** CTest with one test executable `engine_tests`; assert insert/remove/resize, reject-on-negative, bounds and hit test. Use only the standard library.
- **CMake changes:** add `enable_testing()`, the test executable and `add_test(NAME engine_tests ...)`; keep the library target name `canvas_engine`.
- **New files:** `packages/engine/tests/engine_tests.cpp`.
- **Changed files:** `canvas.h`, `canvas.cpp`, `CMakeLists.txt`.
- **Reference:** `src/canvas.cpp` for the existing style; keep functions small and free of I/O.

## Pitfalls

- Bounds checks with strict `>` instead of `>=` drop nodes on the right and bottom edge; test the exact edge.
- `-Wall -Wextra -Wpedantic` is on: unused parameters and sign-compare warnings fail a clean build.
- A `std::find_if` on an empty vector is fine, but `document_bounds()` must not read `max()` results into the output.
- Never touch `src/wasm_bindings.cpp`; the C export list belongs to ENG-02.
- Do not add a test framework dependency; CTest plus assertions is enough for 1.0.

## Edge cases

- Empty document: `node_count() == 0`, bounds all zero, `hit_test` returns `false`.
- Zero-width and zero-height nodes: legal, can never be hit.
- Remove an unknown id: returns `false`, document unchanged.
- The 4,000-node case: insert loop stays under the default CTest timeout.

## Gates

1. `cmake -S packages/engine -B packages/engine/build -DCMAKE_BUILD_TYPE=Debug` → exit 0, "Configuring done".
2. `cmake --build packages/engine/build --parallel` → exit 0, target `canvas_engine` built.
3. `ctest --test-dir packages/engine/build --output-on-failure` → exit 0, "100% tests passed".
4. `python3 .generator/tools/boundaries.py .` → exit 0, no cross-package include.

A gate passes when command, exit code and expected output match; the output is the evidence. If a gate fails: read the cause, fix the code, rerun the gate. Never adjust a test to make it pass.

## Limits

- **Scope:** only `packages/engine/CMakeLists.txt`, `packages/engine/include/engine/canvas.h`, `packages/engine/include/engine/color.h`, `packages/engine/src/canvas.cpp`, `packages/engine/src/color.cpp`, `packages/engine/tests/engine_tests.cpp` — src/wasm_bindings.cpp is forbidden
- **Stop:** max. 2 rework rounds; on an API change beyond this scope, stop and ask
- No new dependencies; C++17 stays the standard

## Output (YAML, no prose)

```yaml
task_id: ENG-01
status: submitted   # submitted | blocked | failed
changed_files: []
evidence: []        # [{gate, command, exit_code, output_tail}]
acceptance: []      # [{id, passed, how}]
open_questions: []
```
