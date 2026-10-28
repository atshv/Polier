# Adapters

Each adapter connects one host to the rules in [`core/`](../core/). An adapter
maps the host's events and tool names onto core calls and turns the decisions
back into the host's format; it holds no scope, board or gate rules of its own.

| Adapter | Host | Status |
|---|---|---|
| [`dsh/`](dsh/) | DeepSeek Harness plugin (`package.json` → `main`) | shipped |
| [`claude-code/`](claude-code/) | Claude Code hooks (`PreToolUse`, `Stop`) | shipped |
| `git/` | git hooks | planned |

The DSH guard decides synchronously inside the harness, so
`dsh/lib/project.mjs` keeps a JavaScript mirror of `core.scope.check_write`
(including the worktree rule and the case-insensitive paths of macOS/Windows)
and of the process-killing detector. `dsh/lib/policy.mjs` mirrors
`core.policy` the same way, because the guard must decide a write before it
happens. Both mirrors are tested against [`core/tests/write_cases.json`](../core/tests/write_cases.json)
and [`core/tests/policy_cases.json`](../core/tests/policy_cases.json); add a
case there whenever a rule changes. Everything else runs the Python core:

| Concern | Shared by every adapter |
|---|---|
| Stop check, board checks, gates | `tools/scope_check.py`, `tools/check.py`, `tools/gate.py` (DSH calls them; Claude Code calls `core/` directly) |
| Claims | `core/claims.py` / `tools/claim.py` — one format for DSH, Claude Code and plain shells; DSH calls the CLI so there is one implementation |
| Runtime slots | `core/slots.py` / `tools/slot.py` — one `.polier-slot` and registry per repo |
| Exclusive gates | `core/locks.py` — one lock file format for `pl_gate` and `tools/gate.py` |
| Policy | `core/policy.py` / `dsh/lib/policy.mjs` — protected paths, dependency manifests, denied and lead-only commands; the approvals store is read from `reviews/approvals/` |
| Execution state | `core/state.py` / `tools/state.py`, `core/runs.py`, `core/approvals.py` — the plan is changed only through these tools, never by an adapter |

The DSH plugin also exposes `pl_next` (dispatch plan) and `pl_state` (board
status against the run record, and lead-only transitions); Claude Code has no
tool registry, so its sessions use the CLI tools through `Bash`.

Runtime state lives outside the working tree, in git's administrative folder:
claims, slots and locks in `<git-common-dir>/polier/` (shared by every
worktree), the Claude Code stop counter under the worktree's own git path.
`board.json` is never written by an adapter; only the lead session runs
`tools/state.py`, and the plan itself is reviewed like code.
