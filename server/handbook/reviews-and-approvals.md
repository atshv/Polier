# Reviews and approvals

Two kinds of decisions keep agents honest: a **review** decides whether a task's result is good enough, an **approval** decides whether an action may happen at all.

## Reviews

1. The task reaches `review` after its gates passed.
2. A reviewer (you or a reviewer session) reads the diff, the brief and the evidence.
3. The verdict goes into `reviews/<ID>.md`:

```markdown
verdict: fail

- The hit test ignores rotated nodes (A3).
- `canvas.cpp` grew past the 400-line limit from ARCHITECTURE.md.
```

4. `pass` allows **→ Done**; `fail` sends the task to `rework` with the findings. **Your Work → Review queue** lists everything waiting for a verdict.

## Approvals

Policy names actions that need the owner: `new_dependency`, `scope_change`, `merge_to_base`, `release`, `reopen_done`, `protected_path` and `state_override`. An agent or you request one:

```bash
python3 tools/approve.py request --action new_dependency --task API-01 --note "httpx for the sync client"
```

It shows up in **Approvals**, the inbox and the dispatch plan. Grant or deny it with a note; the record is committed with the task.

> [!TIP]
> A note on a decision is cheap now and priceless in three months. "Granted: stdlib urllib is too thin for retries" explains more than "ok".
