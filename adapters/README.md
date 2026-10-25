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
and of the process-killing detector. Both are tested against
[`core/tests/write_cases.json`](../core/tests/write_cases.json); add a case
there whenever a rule changes. Everything else runs the Python core:

| Concern | Shared by every adapter |
|---|---|
| Stop check, board checks, gates | `tools/scope_check.py`, `tools/check.py`, `tools/gate.py` (DSH calls them; Claude Code calls `core/` directly) |
| Claims | `core/claims.py` / `tools/claim.py` — one format for DSH, Claude Code and plain shells; DSH calls the CLI so there is one implementation |
| Runtime slots | `core/slots.py` / `tools/slot.py` — one `.polier-slot` and registry per repo |
| Exclusive gates | `core/locks.py` — one lock file format for `pl_gate` and `tools/gate.py` |

Runtime state lives outside the working tree, in git's administrative folder:
claims, slots and locks in `<git-common-dir>/polier/` (shared by every
worktree), the Claude Code stop counter under the worktree's own git path.
`board.json` is never written by an adapter; only the lead edits the plan.
