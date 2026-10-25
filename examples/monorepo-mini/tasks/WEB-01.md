# WEB-01 — Toolbar and stage in the UI kit

## Goal

The UI kit renders the canvas stage and toolbar with design tokens and covers their states in component tests.

**Why:** WEB-02 assembles the app shell from these components. The UI section of this brief is the reference for every later UI change.

**Satisfies:** D4

## Scope

- **Package:** `packages/ui-kit` — this task writes only inside the UI kit.
- `src/components/Toolbar.tsx`: zoom buttons with accessible names and a slot for extra controls
- `src/components/Stage.tsx`: the canvas host that reports the node count from the engine handle
- `src/theme.css`: the design tokens used by both components
- `src/index.ts`: the package exports
- `tests/components.test.tsx`: rest, hover, focus and disabled states, plus the accessible names

## Out of scope

- drawing, panning and node selection — the engine and WEB-02 own behaviour
- the app route, layout and sync client (WEB-02)
- new tokens: a value that is not in `src/theme.css` is a finding, not a new rule
- dark mode

## Acceptance

A1 WHEN `Stage` receives a non-null `CanvasHandle`, THEN the system SHALL render the node count from `handle.nodeCount()`; with a null handle it SHALL render `0 nodes` without an error.

A2 WHEN `Toolbar` is rendered, THEN the system SHALL expose two buttons with the accessible names "Zoom in" and "Zoom out" and SHALL call the matching callback once per click.

A3 WHEN a toolbar button is hovered or focused, THEN the system SHALL transition the background over 120 ms (`--motion-fast`) and SHALL show a focus outline of 2 px in `--accent` with a 2 px offset (P-2).

A4 WHEN a component stylesheet is inspected, THEN the system SHALL use only tokens from `src/theme.css`; no hex colour, no pixel literal in `components/` (AD-5).

A5 WHEN `npm test` runs in `packages/ui-kit`, THEN the system SHALL pass the component tests for rest, hover, focus and disabled states.

## Context pack

**Read exactly:**

- `packages/ui-kit/ARCHITECTURE.md` (P-1 … P-4)
- `packages/ui-kit/src/theme.css` (all tokens)
- `packages/ui-kit/src/components/Stage.tsx` and `Toolbar.tsx` (current components)
- `docs/design-rules.md` (tokens, states, accessibility minimums)
- `packages/engine/types/index.d.ts` (`CanvasHandle`)

**Do not read:** the app route, the sync service, other briefs.

**Budget:** ≤ 15,000 tokens input.

## UI specification

| Element | Property | Value | Token |
| --- | --- | --- | --- |
| toolbar | height | 48 px | `--space-8` |
| toolbar | horizontal padding | 16 px | `--space-4` |
| toolbar | gap between buttons | 8 px | `--space-2` |
| toolbar button | min width / height | 48 px / 32 px | `--space-8` / `--space-6` |
| toolbar button | border radius | 8 px | `--radius-sm` |
| toolbar button | background transition | 120 ms | `--motion-fast` |
| toolbar button | focus outline | 2 px, offset 2 px | `--accent` |
| stage | top border | 1 px | `--border` |
| stage count label | font size | 13 px | `--text-sm` |
| stage count label | right / bottom inset | 16 px / 12 px | `--space-4` / `--space-3` |

**States:** rest — token background, token border. Hover — background `--border`, 120 ms. Pressed — scale 0.97, no colour change. Focus — 2 px `--accent` outline with 2 px offset, never removed. Disabled — 0.4 opacity, no hover. Selected, dragging, saving and error do not occur in these two components; write `n/a` for them in the test names.

**Do not:** add hex colours, change the spacing scale, animate layout properties, remove the focus outline, change the app route.

**Evidence screenshots:** `reviews/evidence/WEB-01-toolbar-stage-before-1440x900.png` and `…-after-1440x900.png`, plus the `390x844` pair.

## Pitfalls

- React 18 `react-jsx` needs no `import React`; it would be dead code.
- A click test must assert the callback count; a rendered button without a handler passes the wrong test.
- Vitest with jsdom needs `environment: jsdom`; without it the component tests fail on `document`.
- Removing the browser default focus ring without replacement fails A3 and the accessibility minimums.
- `CanvasHandle` is a type-only import; a runtime import from `@canvas/engine` would pull WASM into the component test.

## Edge cases

- `CanvasHandle.nodeCount()` returns `0`: render `0 nodes`, not an empty element.
- A `null` handle: the stage still renders with zoom `1`.
- Rapid double click: the callback fires twice.
- Long labels in `children`: the toolbar keeps 48 px height and does not wrap.

## Gates

1. `npm run typecheck` in `packages/ui-kit` → exit 0, no type errors.
2. `npm test` in `packages/ui-kit` → exit 0, all component tests pass.
3. `npx playwright test --grep @visual` in `apps/web` → exit 0, screenshots within tolerance.
4. `python3 .generator/tools/boundaries.py .` → exit 0, the kit imports only `packages/engine`.

A gate passes when command, exit code and expected output match; the output is the evidence. If a gate fails: read the cause, fix the code, rerun the gate. Never adjust a test to make it pass.

## Limits

- **Scope:** only `packages/ui-kit/src/index.ts`, `packages/ui-kit/src/components/Toolbar.tsx`, `packages/ui-kit/src/components/Stage.tsx`, `packages/ui-kit/src/theme.css`, `packages/ui-kit/tests/components.test.tsx` — no app or service file
- **Stop:** max. 2 rework rounds; when a token is missing, stop and ask, do not inline a value
- No new dependencies; no change to `apps/web`

## Output (YAML, no prose)

```yaml
task_id: WEB-01
status: submitted   # submitted | blocked | failed
changed_files: []
evidence: []        # [{gate, command, exit_code, output_tail}]
acceptance: []      # [{id, passed, how}]
open_questions: []
```
