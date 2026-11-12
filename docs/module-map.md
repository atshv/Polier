# Module Structure: Polier next

> Detail document for `ARCHITECTURE.md`. Paths are relative to the repository root. Existing modules in plain text, new ones **bold**.

## Layers

| Layer | Folder | Purpose | May import | May not import |
|---|---|---|---|---|
| Adapters | `plugin/index.mjs`, `claude/server.mjs`, `claude/hook.mjs` | wire the tools into DSH and Claude Code | `plugin/lib/` | `core/`, `tools/` by import |
| Harness-neutral tools | `plugin/lib/` (`tools.mjs` gains **`pl_change`**, **`pl_quick`**) | tool definitions, live context, guard forwarding | Node built-ins; run `tools/*.py` as processes | adapters |
| Commands | `tools/` (**`retro.py`**, **`change.py`**, **`quick.py`**) | one CLI per rule set | `core/` | another tool, plugin code |
| Rules | `core/` (**`retro.py`**, **`changes.py`**, **`quick.py`**) | the one implementation of each rule | standard library, other `core/` modules | `tools/`, plugin code |
| Templates | `templates/` (**`change-proposal.md`**) | documents a project copies | — | — |
| Black-box suite | **`evals/<case>/`** with `prompt.md`, `case.yaml`, `graders/`, `fixture.sh` | process scenarios for `claude plugin eval` | nothing; drives the plugin from outside | any module |

## Rules

- `core/quick.py` reads the board, the line and the catalog through `core/board.py` and `core/factory.py`; it never writes. `tools/quick.py` writes the task through `core/board.py` and the brief from `templates/task-brief.md`.
- `core/changes.py` owns `changes/<ID>/proposal.md`: parse, validate the delta, apply it to the target headings. Approvals come from `core/approvals.py`.
- `core/retro.py` reads `runs/`, `reviews/`, `reviews/approvals/`, `board.json` and `factory.json` through the existing loaders; one function per error class.
- Tests: `tests/test_retro.py`, `tests/test_change_cli.py`, `tests/test_quick_cli.py`, `core/tests/test_changes.py`, `core/tests/test_quick.py`, and the new tools in `plugin/test/` and `claude/test/`, all on fixtures in `tests/fixtures/`.
- `evals/results/` is gitignored; `evals/` is not in the npm package.
