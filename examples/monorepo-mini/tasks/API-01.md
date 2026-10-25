# API-01 — Sync service over the state contract

## Goal

The sync service validates document state against contract 1.0.0 and serves it on the API slot port.

**Why:** WEB-02 wires the app to this service. The version check is what keeps a browser built from one revision compatible with a service built from another.

**Satisfies:** D4

## Scope

- `src/state.ts`: the `CanvasState` types and `validateState` mirroring `contracts/state/state.schema.json`
- `src/server.ts`: the HTTP surface — `GET /health` and `POST /documents/:id`
- `src/index.ts`: the public exports of the service package
- `tests/server.test.ts`: contract version rejection, health, accepted revision and monotonic revisions

## Out of scope

- WebSocket fan-out beyond the in-memory broadcast list; a real transport is a later task
- persistence: 1.0 keeps the document in memory (P-3)
- accounts, authorisation, rate limits
- rendering or UI code of any kind (AD-2)

## Acceptance

A1 WHEN a document with a `version` other than `CONTRACT_VERSION` arrives, THEN the system SHALL reject it with HTTP 409 and a problem list, and SHALL not change the stored document (P-1).

A2 WHEN `GET /health` is called on the API slot port, THEN the system SHALL answer HTTP 200 with the JSON body `{"status":"ok","contract":"1.0.0"}`.

A3 WHEN a valid document is posted, THEN the system SHALL accept it, increment the revision and broadcast the accepted revision to every connected client (P-2).

A4 WHEN `npm test` runs in `services/sync`, THEN the system SHALL pass the unit tests for validation, health and revision monotonicity.

## Context pack

**Read exactly:**

- `services/sync/ARCHITECTURE.md` (P-1 … P-3)
- `services/sync/src/state.ts` (types and current validator)
- `services/sync/src/server.ts` (current handlers)
- `contracts/state/state.schema.json` (required fields and `$defs`)
- `contracts/state/README.md` (version rules)
- `docs/environments.md` (variable names and the smoke URL)
- `docs/gates/node-ts.md` (gates and pitfalls)

**Do not read:** the app sources, the UI kit, other briefs.

**Budget:** ≤ 15,000 tokens input.

## Specifications

- **Package:** `services/sync` — this task writes only inside the service.
- **Runtime:** Node 22, TypeScript, `node:http` only; no framework, no new dependency (sandbox and bundle size).
- **Port:** read `PORT` from the environment; the slot file sets it to `4100 + 50·slot + 1`. A missing `PORT` is a startup error, not a default.
- **Validation:** `validateState` checks `contract`, `version`, `documentId`, `nodes`, `edges` and `viewport.zoom`; it returns one line per problem, and an empty array means accepted. It must match the schema in `contracts/state/`, not a second dialect.
- **Revision:** a module-level counter per document; broadcast only accepted revisions, in order; a client that reconnects gets the latest revision.
- **Health:** `GET /health` answers without touching the document; its body is the smoke-check contract.
- **New files:** none beyond the scoped test file.
- **Changed files:** `src/server.ts`, `src/state.ts`, `src/index.ts`, `tests/server.test.ts`.
- **Reference:** `src/state.ts` for the validator shape; keep it dependency free.

## Pitfalls

- A bare `http` import is treated as a package by Node; use the `node:http` prefix.
- Rejecting with 409 must not mutate the stored document first — validate, then swap.
- A revision must never go backwards after a reconnect; test the ordering, not only the count.
- The service is reachable from the browser: never log document bodies or environment values.
- Tests must bind port `0` and close the server, or the suite hangs.

## Edge cases

- Empty `nodes` and `edges` are a valid document.
- A body larger than 1 MB is rejected with 413 before validation.
- Malformed JSON returns 400, a wrong contract version returns 409, a missing field returns 422.
- Two clients connected: both receive the same revision in the same order.

## Gates

1. `npm run typecheck` in `services/sync` → exit 0, no type errors.
2. `npm test` in `services/sync` → exit 0, all unit tests pass.
3. `python3 tools/contract_check.py` → exit 0, the service mirrors the current contract version.
4. `python3 .generator/tools/boundaries.py .` → exit 0, no cross-package import.
5. `python3 .generator/tools/smoke.py --url http://localhost:4101 --expect-status 200 --path /health` → exit 0 after a local start.

A gate passes when command, exit code and expected output match; the output is the evidence. If a gate fails: read the cause, fix the code, rerun the gate.

## Limits

- **Scope:** only `services/sync/src/server.ts`, `services/sync/src/state.ts`, `services/sync/src/index.ts`, `services/sync/tests/server.test.ts` — no contract or engine change
- **Stop:** max. 2 rework rounds; on a contract change, stop and ask (a new contract version is its own task)
- No new dependencies; no persistence

## Output (YAML, no prose)

```yaml
task_id: API-01
status: submitted   # submitted | blocked | failed
changed_files: []
evidence: []        # [{gate, command, exit_code, output_tail}]
acceptance: []      # [{id, passed, how}]
open_questions: []
```
