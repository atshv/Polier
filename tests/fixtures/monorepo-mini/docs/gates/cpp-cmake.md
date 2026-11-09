# Gate Catalogue: C++ / CMake

> Candidate gates for `packages/engine`. The plan uses `configure`, `build` and `cpp-unit`; add a row here when a task adopts another gate. Run the commands from the project root; the build folders are gitignored.

| Gate | Command shape | Expected |
|---|---|---|
| `configure` | `cmake -S packages/engine -B packages/engine/build -DCMAKE_BUILD_TYPE=Debug` [VERIFY: preset and CMake version] | exit 0, "Configuring done" |
| `build` | `cmake --build packages/engine/build --parallel` [VERIFY: generator from CI] | exit 0, library target built |
| `cpp-unit` | `ctest --test-dir packages/engine/build --output-on-failure` [VERIFY: CTest version and test names] | exit 0, "100% tests passed" |
| `cpp-format` | `clang-format --dry-run --Werror packages/engine/include packages/engine/src` [VERIFY: add `.clang-format` and pin the version before adopting this gate] | exit 0, no formatting changes |
| `cpp-tidy` | `clang-tidy -p packages/engine/build packages/engine/src/*.cpp` [VERIFY: `compile_commands.json` exists] | exit 0, no findings |

- The library target is `canvas_engine`; the WASM harness target is `canvas_engine_wasm` and is compiled only under Emscripten (`CMakeLists.txt`).
- A release config exists only once the project defines one: `-DCMAKE_BUILD_TYPE=Release` [VERIFY: from the CI image].

## Pitfalls

- A stale `build/` hides changes: configure into a fresh directory or clean the target. Never commit `build/`.
- When the project adds `CMakePresets.json`, its presets override flags; use them instead of inventing `-D` options.
- Sanitizers are slower and platform-specific; give them their own gate [VERIFY: from the CI image].
- Compiler version and C++ standard come from `docs/versions.md`; the engine is C++17 and stays there.
- Tests that need a file or port use the slot paths; a test must not leave a process running. Do not stop processes you did not start.
