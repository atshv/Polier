# services/sync

## Commands

- **Build:** `npm run build` (`tsc -p tsconfig.json`).
- **Typecheck:** `npm run typecheck` → no type errors.
- **Tests:** `npm test` (`vitest run`) → all green.
- **Server:** `node --experimental-strip-types src/server.ts` on the slot port [VERIFY: Node 22 flag from the pinned docs].

## Deviations from the root `AGENTS.md`

- Every handler validates the contract version before touching the document; a mismatch returns 409 with the problem list.
- Read the port from `PORT`; the slot file sets it, never a literal in code.
- No database in 1.0: state is in memory, so a restart drops the document.

## Pitfalls

- Node resolves `node:http` only with the `node:` prefix; a bare `http` import would be treated as a package.
- A client that reconnects must receive the latest revision, not the one it reconnects with.
- The service is reachable from the browser: never log document content or secrets.
