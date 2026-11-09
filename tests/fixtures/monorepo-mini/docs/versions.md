# Versions: canvas-mini

> Every dependency from every `package.json`, `CMakeLists.txt` and CI workflow appears here. Exact versions only; `[VERIFY: …]` marks a value the first build task confirms against the pinned toolchain image.

| Tool / library | Exact version | Source URL | Date checked | Approved by |
| --- | --- | --- | --- | --- |
| Node.js | 22.11.0 [VERIFY: pinned in the CI image] | https://nodejs.org/en/blog/release/v22.11.0 | 2026-10-17 | CI owner |
| TypeScript | 5.6.3 | https://registry.npmjs.org/typescript/5.6.3 | 2026-10-17 | lead |
| Next.js | 15.0.0 | https://registry.npmjs.org/next/15.0.0 | 2026-10-17 | web owner |
| React | 18.3.1 | https://registry.npmjs.org/react/18.3.1 | 2026-10-17 | web owner |
| React DOM (`react-dom`) | 18.3.1 | https://registry.npmjs.org/react-dom/18.3.1 | 2026-10-17 | web owner |
| `@types/node` | 22.8.1 | https://registry.npmjs.org/@types%2fnode/22.8.1 | 2026-10-17 | sync owner |
| `@types/react` | 18.3.11 | https://registry.npmjs.org/@types%2freact/18.3.11 | 2026-10-17 | web owner |
| Vitest | 2.1.4 | https://registry.npmjs.org/vitest/2.1.4 | 2026-10-17 | lead |
| `@playwright/test` | 1.48.0 | https://registry.npmjs.org/@playwright%2ftest/1.48.0 | 2026-10-17 | app owner |
| CMake | 3.28.3 [VERIFY: pinned in the CI image] | https://cmake.org/cmake/help/v3.28/release/3.28.html | 2026-10-17 | engine owner |
| Emscripten | 3.1.61 [VERIFY: pinned in the CI image] | https://github.com/emscripten-core/emscripten/releases/tag/3.1.61 | 2026-10-17 | engine owner |
| C++ standard | C++17 | https://isocpp.org/std/the-standard | 2026-10-17 | engine owner |
| `@canvas/engine` | 0.1.0 (workspace) | `packages/engine/package.json` | 2026-10-17 | engine owner |
| `@canvas/ui-kit` | 0.1.0 (workspace) | `packages/ui-kit/package.json` | 2026-10-17 | UI owner |
| `@canvas/sync` | 0.1.0 (workspace) | `services/sync/package.json` | 2026-10-17 | sync owner |

## Rules

1. Every dependency of a manifest, lockfile, `CMakeLists.txt` or CI workflow appears in the table, including dev dependencies, browsers and build tools.
2. Versions are exact and come from the manifest or lockfile, or from upstream release notes with a URL. The date is the day the value was checked.
3. `[VERIFY: …]` marks a value still to confirm against the pinned toolchain; it must be resolved before the first release tag. No `latest`, no ranges in this table.
4. A version change updates the manifest, the lockfile and this table in the same task. No silent upgrades.
5. `tools/check.py` in the Polier copy warns when a manifest dependency is missing here; treat that warning as an error before a release.
