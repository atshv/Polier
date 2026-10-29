# Run agents headless

The dashboard can start an agent for a task, stream its transcript and record its token use. The session runs with the same hooks and scope rules as an interactive one.

## Configure the provider

**Settings → Sessions** holds the provider command (machine-local, never committed). The default runs the Claude Code CLI non-interactively:

```bash
claude -p --output-format stream-json --verbose --permission-mode acceptEdits \
  --allowedTools "Bash Read Write Edit Glob Grep TodoWrite" \
  --settings <generated settings.json> "<composed prompt>"
```

The generated settings install the Polier hooks with `POLIER_ROLE` and `POLIER_TASK`, so writes outside the task are denied.

## Start a session

- From a task: the drawer's **Session** tab → role, optional note, optional worktree → **Start**.
- From **Sessions**: pick a task (or none) and a role.
- From the CLI:

```bash
python3 tools/session.py run ENG-01 --role worker --worktree --note "focus on the hit test"
python3 tools/session.py list
```

## Roles

| Role | Does | May write |
|---|---|---|
| `worker` | implements the task | the task's `scope.write` |
| `reviewer` | reviews and writes a verdict | `reviews/<ID>.md` |
| `lead` | runs gates and status changes | everything the policy allows |
| `generator` | writes the plan | the planning files |

## Watch and stop

The transcript streams into the console. **Stop** ends the process; the claim is released and the attempt is recorded. Tokens reported by the provider land in `runs/<ID>.json` and count against `budget.max_tokens_per_task`.

> [!WARNING]
> Sessions run real commands in your project. Start them on purpose, prefer a worktree for parallel work, and never expose the dashboard to a network without a token.
