# Gate Catalogue: Node / TypeScript

> Candidate gates for the TypeScript packages `packages/ui-kit`, `services/sync` and `apps/web`. The plan uses `types`, `tests`, `e2e`, `visual-diff` and `boundaries`; add a row here when a task adopts another gate. Run every command in the package folder.

| Gate | Command shape | Expected |
|---|---|---|
| `lint` | `npm run lint` in the package [VERIFY: script added with the first test task] | exit 0, no lint errors |
| `types` | `npm run typecheck` (`tsc --noEmit`) [VERIFY: script name from `package.json`] | exit 0, no type errors |
| `tests` | `npm test` (`vitest run`) [VERIFY: runner from `package.json`] | exit 0, all tests pass |
| `build` | `npm run build` [VERIFY: script from `package.json`] | exit 0, build output written |
| `e2e` | `npx playwright test` in `apps/web`, exclusive resource `e2e` | exit 0, full flow green |
| `visual-diff` | `npx playwright test --grep @visual` in `apps/web` | exit 0, screenshots within tolerance |
| `boundaries` | `python3 .generator/tools/boundaries.py .` | exit 0, no cross-package import |

- Single test: `npm test -- <pattern>`, e.g. `npm test -- Stage` in the UI kit.
- Install exactly as CI does (`npm ci`); a gate never installs packages.
- TypeScript and Vitest versions come from `docs/versions.md`; do not upgrade them inside a task.

## Pitfalls

- Script names differ per package; take them from `package.json`, not from habit.
- Watch mode never exits: a gate runs once and stops.
- `node_modules/`, `.next/`, coverage and test caches are gitignored; a gate that writes tracked files is broken.
- e2e uses the slot ports from `.polier-slot`, never a hard-coded 3000 or 4100.
- The app imports `@canvas/engine`, `@canvas/ui-kit` and `@canvas/sync` through the workspace names; a relative import across packages fails the boundaries gate.
