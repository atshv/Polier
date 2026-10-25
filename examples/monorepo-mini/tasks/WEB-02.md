# WEB-02 — Web app shell and sync wiring

## Goal

The web app loads the engine, renders the UI kit and exchanges document state with the sync service on its slot port.

**Why:** It is the last functional task before release and proves the contract end to end in a browser: engine, kit, service and app under one flow.

**Satisfies:** D4, D5

## Scope

- `src/app/page.tsx`: the editor route that composes `Toolbar` and `Stage`
- `src/app/layout.tsx`: the root layout, metadata and the stylesheet import
- `src/lib/sync-client.ts`: the transport client — fetch the document, validate it, post changes
- `package.json` and `tsconfig.json`: the e2e script and the workspace path aliases
- `tests/e2e/canvas.spec.ts`: the Playwright flow for draw, reload and reconnect

## Out of scope

- geometry or sync rules: the engine owns geometry, the service owns ordering (AD-2)
- new components in the UI kit (WEB-01)
- persistence, accounts and conflict resolution (after 1.0)
- preview or production deployment (REL-01)

## Acceptance

A1 WHEN the app loads on the slot web port, THEN the system SHALL render `Toolbar` and `Stage` from `@canvas/ui-kit` and SHALL show the node count of the document received from the sync service.

A2 WHEN the service returns a document with a contract version other than `1.0.0`, THEN the system SHALL run `validateState`, keep the previous document and show an error state instead of rendering the message (P-2).

A3 WHEN the service is unreachable, THEN the system SHALL show a retry state instead of a crash and SHALL log no environment value or document body.

A4 WHEN `npx playwright test` runs against the slot ports, THEN the system SHALL pass the flow — draw a rectangle, reload and see the node again — with the `e2e` resource held exclusively (the `exclusive` list of this task).

A5 WHEN `python3 .generator/tools/smoke.py --url http://localhost:4100 --expect-status 200 --path /` runs after the deploy step, THEN the system SHALL exit 0 and write a smoke record.

## Context pack

**Read exactly:**

- `apps/web/ARCHITECTURE.md` (P-1 … P-4)
- `apps/web/src/app/page.tsx` (current composition)
- `packages/ui-kit/src/index.ts` (exports of `Stage` and `Toolbar`)
- `services/sync/src/index.ts` (exports, `CONTRACT_VERSION`)
- `contracts/state/README.md` (version rules)
- `docs/design-rules.md` (layout breakpoints and states)
- `docs/environments.md` (variable names)
- `docs/gates/node-ts.md` (e2e and boundaries gates)

**Do not read:** engine sources, the UI kit internals beyond its exports, other briefs.

**Budget:** ≤ 15,000 tokens input.

## Specifications

- **Package:** `apps/web` — this task writes only inside the app.
- **Composition:** the route imports `Stage` and `Toolbar` from `@canvas/ui-kit`, the `CanvasHandle` type from `@canvas/engine` and `CanvasState` plus `validateState` from `@canvas/sync` (P-1).
- **Sync client:** `createSyncClient(baseUrl)` with `load(documentId)`, `apply(revision)` and `subscribe(listener)`; base URL from `NEXT_PUBLIC_SYNC_URL`, never a literal host (P-4).
- **Error mapping:** network failure → retry state; 409 version mismatch → error state with the contract version; 422 invalid fields → error state naming the first field.
- **Validation:** every message passes `validateState` before it reaches the stage; the previous document stays on screen (P-2).
- **Styles:** the layout imports the token stylesheet and sets the app shell only with tokens (P-3).
- **Changed files:** `src/app/page.tsx`, `package.json`, `tsconfig.json`; new files `src/app/layout.tsx`, `src/lib/sync-client.ts`, `tests/e2e/canvas.spec.ts`.
- **Reference:** `services/sync/src/index.ts` for the contract version constant.

## Pitfalls

- Next.js 15 treats `page.tsx` as a server component by default; the sync client needs `"use client"` at the top.
- Playwright must use the slot ports from `.polier-slot`; a hard-coded 3000 collides with another worktree.
- `e2e` is an exclusive resource: run it through the gate runner so the lock is taken, not with a bare command in a second session.
- A failed fetch in a server component is rendered as a 500 page; keep the fetch in the client effect.
- Do not import a package's internal file; only the public entry point or the contract.

## Edge cases

- Empty document: the stage shows `0 nodes`, no error.
- Service restart while the page is open: the client reconnects and receives the latest revision.
- Two tabs open: both show the same revision after an accepted change.
- A document id with special characters is URL-encoded before it reaches the service.

## Gates

1. `npm run typecheck` in `apps/web` → exit 0, no type errors.
2. `npm test` in `apps/web` → exit 0, all unit tests pass.
3. `npx playwright test` in `apps/web` → exit 0, the full flow is green (exclusive `e2e`).
4. `python3 .generator/tools/smoke.py --url http://localhost:4100 --expect-status 200 --path /` → exit 0, `SMOKE OK`.
5. `python3 .generator/tools/boundaries.py .` → exit 0, the app imports only allowed packages.

A gate passes when command, exit code and expected output match; the output is the evidence. If a gate fails: read the cause, fix the code, rerun the gate. Never adjust a test to make it pass.

## Limits

- **Scope:** only `apps/web/src/app/page.tsx`, `apps/web/src/app/layout.tsx`, `apps/web/src/lib/sync-client.ts`, `apps/web/package.json`, `apps/web/tsconfig.json`, `apps/web/tests/e2e/canvas.spec.ts` — no engine, kit or service change
- **Stop:** max. 2 rework rounds; on a contract change, stop and ask
- No new dependencies; no change outside `apps/web`

## Output (YAML, no prose)

```yaml
task_id: WEB-02
status: submitted   # submitted | blocked | failed
changed_files: []
evidence: []        # [{gate, command, exit_code, output_tail}]
acceptance: []      # [{id, passed, how}]
open_questions: []
```
