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
`dsh/lib/project.mjs` keeps a JavaScript mirror of `core.scope.check_write`.
Both are tested against [`core/tests/write_cases.json`](../core/tests/write_cases.json);
add a case there whenever a rule changes. Stop check, gates and board checks
run the Python core through `tools/`. The Claude Code hooks are Python and call
`core/` directly.
