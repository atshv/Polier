# Architecture: Polier next

**As of:** 2026-11-12 · **Status:** draft for the owner · **Owner:** lead

> **Size budget:** 400–600 words, hard limit 800.

## 1. Purpose and non-goals

Polier next adds four features to Polier (`docs/concept.md`, first stage F1–F4): process evals, a retro over project records, change proposals for a shipped product and a quick track for small changes. Code and plan share the Polier repository root, so the guard and the stop check protect the build tasks (`docs/architecture.md` describes the package as it is).

**Non-goals:** no hosted service or telemetry, no own spec format, no autonomous change to Polier.

## 2. Hard constraints

- **Platform/version:** Python 3.9+ standard library, Node 20+ without a build step, Claude Code ≥ 2.1.269 for evals (`docs/versions.md`).
- **Runtime map:** everything runs on the maintainer's machine or a CI runner (Python tools, the MCP server, hooks); only eval runs call Anthropic's API; nothing runs on a server of ours.
- **Data and network:** project records stay local; evals call the model provider only.
- **Legal/rules:** MIT; eval runs follow the provider's terms with the maintainer's own credentials.
- **Secrets/backend:** no backend; the one secret is the eval API key in CI (`docs/environments.md`).
- **Time/budget:** no deadline; eval cost capped per run (ADR-0001).
- **Language:** English everywhere; README also German.

## 3. System shape and module structure

The existing one-way chain stays and the new code joins its layers (`docs/module-map.md`):

| Layer | Folder | May | May not |
| --- | --- | --- | --- |
| Adapters | `plugin/index.mjs`, `claude/` | call the harness-neutral tools | hold a rule |
| Harness-neutral tools | `plugin/lib/` | run `tools/*.py`, read files | write a record itself |
| Commands | `tools/` | call `core/` | import another tool |
| Rules | `core/` | standard library | import tools or plugins |
| Black-box suite | `evals/` | drive the installed plugin | import any module |

**Rule:** dependencies point down: adapters → plugin/lib → tools → core → files. `evals/` sees Polier only from outside.

## 4. Invariants (AD-1 … AD-n)

| ID | Rule | Binds | Prevents |
| --- | --- | --- | --- |
| AD-1 | An eval grader decides on outcomes (files, refusals, records) in both arms; graders on Polier tool calls are `arm: with-only` indicators. | `evals/` | a delta inflated by graders the baseline cannot pass |
| AD-2 | `retro` opens project folders read-only and writes only to the path the maintainer names. | `core/retro.py`, `tools/retro.py` | changing or leaking a project through the retro |
| AD-3 | A change proposal is merged only by `tools/change.py apply`, after a granted `scope_change` approval and with every linked task done; the delta names its target by `file#heading`. | `core/changes.py`, `changes/` | living docs that drift from what was approved |
| AD-4 | A quick task is an ordinary board task with `track: quick`; the same state machine, gates, review and handoff apply. Only `core/quick.py` decides whether a request qualifies. | `core/quick.py`, `core/board.py`, `core/state.py` | a second, weaker path to `done` |
| AD-5 | New `pl_*` tools are defined once in `plugin/lib/tools.mjs` and forward to `tools/*.py`. | `plugin/lib/`, `claude/` | a feature that works in one harness only |

## 5. Boundaries and ownership

| Area | Belongs to | Write | Read |
| --- | --- | --- | --- |
| `core/`, `tools/` | rules, commands | builder tasks | everyone |
| `plugin/lib/tools.mjs` | tool definitions | builder tasks | both adapters |
| `evals/` | process suite | builder tasks; results only by `claude plugin eval` | maintainer |
| `templates/change-proposal.md` | template | builder task | lead agents |
| plan files (`board.json`, `factory.json`, `docs/concept.md` …, `tasks/`) | the line | lead, through the tools | everyone |

## 6. Quality gates

- **Tests:** `npm test` → every Node and Python suite passes.
- **Checks:** `npm run check` → `OK: generated pages current, …`.
- **Plugin:** `claude plugin validate . --strict` → `Validation passed`.
- **Fixtures:** `python3 tools/check.py tests/fixtures/minimal-cli` → `OK`.
- **E2E/acceptance:** D1–D4 in `docs/quality.md`; D1 is `npm run evals` with a with-arm threshold of 1.0 and a positive delta per case.
- **Review:** independent; diff + criteria + gate output.

## 7. Open / deliberately undecided (deferred)

- Evals for DSH — after F1, when DSH offers a headless eval path.
- F5–F9 — a later stage.

## 8. References

- Module structure: `docs/module-map.md`
- Decisions: `docs/adr/`
- Versions: `docs/versions.md`
- Environments and secrets: `docs/environments.md`
- Research: `docs/research/`
