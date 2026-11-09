# Architecture

```mermaid
flowchart LR
  human([Owner]) -- plain language --> agent[DSH agent]
  agent -- pl_* tools --> plugin[plugin/]
  plugin -- live context + guide --> agent
  plugin -- approval prompt --> human
  plugin -- guard, stop check --> agent
  plugin -- runs --> tools[tools/*.py]
  tools --> core[core/ rules]
  core --> files[(board.json · factory.json · policy.json · runs/ · reviews/)]
  catalog[(factory/catalog.json)] --> core
```

- **`plugin/`** is the only part that knows DeepSeek Harness. `index.mjs` wires the services; `lib/context.mjs` builds the `<polier>` block and the guide, `lib/guard.mjs` the write and command guard and the stop check, `lib/tools.mjs` the `pl_*` tools, `lib/session.mjs` roles and claims, `lib/factory.mjs` a read-only view of the line.
- **`tools/`** are command-line programs, one per rule set. The plugin calls them for every write, so a rule has one implementation; headless runs call them directly.
- **`core/`** holds the rules in Python's standard library: board validation, the state machine, gates and evidence, approvals, claims, slots, policy, the factory line.
- **Project files** are the only state. Nothing lives in a database or a service; every record is committed with the work.

Dependencies point one way: plugin → tools → core → files. Every rule exists once, in `core/`: the plugin asks `tools/guard.py` before a write or a command and shows its answer.
