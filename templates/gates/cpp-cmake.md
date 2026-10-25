# Gate Catalogue: C++ / CMake

> Copy the gates the project has to `docs/gates/cpp-cmake.md`; delete the rest. Replace every `<...>`; use only flags verified in the manifest or docs.

| Gate | Command shape | Expected |
| --- | --- | --- |
| `configure` | `cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug` [VERIFY: presets and CMake version] | exit 0, "Configuring done" |
| `build` | `cmake --build build --parallel` [VERIFY: generator and target] | exit 0, "Built target …" |
| `cpp-unit` | `ctest --test-dir build --output-on-failure` [VERIFY: CTest version and test names] | exit 0, "100% tests passed" |
| `cpp-format` | `clang-format --dry-run --Werror <paths>` [VERIFY: config file and version] | exit 0, no formatting changes |
| `cpp-tidy` | `clang-tidy <files> -p build` [VERIFY: compile_commands.json exists] | exit 0, no findings |

- Target name and executable come from `CMakeLists.txt`; do not rename a target inside a gate.
- A release config exists only if the project defines it: `-DCMAKE_BUILD_TYPE=Release` [VERIFY: from docs].

## Pitfalls

- A stale `build/` hides changes: configure into a fresh directory or clean the target. Never commit `build/`.
- `CMakePresets.json` overrides flags; use the presets instead of inventing `-D` options.
- Sanitizers (ASan, UBSan) are slower and platform-specific; give them their own gate [VERIFY: from docs].
- Compiler version and C++ standard come from the project docs; pin them in `docs/versions.md`.
- Tests that need a file or port use the slot's paths and ports; a test must not leave a process running.
- Do not stop processes you did not start: no `kill`, `pkill` or `killall`.
