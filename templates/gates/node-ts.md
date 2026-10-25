# Gate Catalogue: Node / TypeScript

> Copy the gates the project has to `docs/gates/node-ts.md`; delete the rest. Replace every `<...>`; use only flags verified in the manifest or docs.

| Gate | Command shape | Expected |
| --- | --- | --- |
| `lint` | `npm run lint` [VERIFY: from manifest/docs] | exit 0, no lint errors |
| `types` | `npm run typecheck` or `npx tsc --noEmit` [VERIFY: script name and tsconfig] | exit 0, no type errors |
| `tests` | `npm test` or `npm run test:unit` [VERIFY: from manifest/docs] | exit 0, all tests pass |
| `build` | `npm run build` [VERIFY: from manifest/docs] | exit 0, build artifacts written |
| `boundaries` | `python3 <package>/tools/boundaries.py .` (profile L) | exit 0, no cross-package import |

- Single test: the runner's own selector, e.g. `npm test -- <pattern>` [VERIFY: from manifest/docs].
- Install exactly as CI does (`npm ci` or the project's package manager) [VERIFY: from manifest/docs]; a gate never installs packages.

## Pitfalls

- Script names differ per project; take them from `package.json`, not from habit.
- Watch mode never exits: a gate must run once and stop.
- Node version comes from `.nvmrc`, `engines` or the CI config; record it in `docs/versions.md`.
- `node_modules/`, build output, coverage and test caches belong in `.gitignore`; a gate that writes tracked files is broken.
- e2e is separate (`playwright.md`); use the slot's ports, never a hard-coded 3000/3101.
