# Claude Code adapter

Hooks that apply Polier's write guard and stop check in Claude Code. They call
only [`core/`](../../core/); the rules are the same as in the DeepSeek Harness
plugin.

| Hook | Event | Effect |
|---|---|---|
| `hook.py pre-tool-use` | `PreToolUse` on `Write`, `Edit`, `MultiEdit`, `NotebookEdit`, `Bash` | A write outside the running task's scope is denied with the reason. For `Bash`, the files the command visibly writes are checked (redirections, `tee`, `cp`/`mv`, `rm`, `sed -i`, …; see [`core/shell.py`](../../core/shell.py)). |
| `hook.py stop` | `Stop` | Changed files (`git status`) outside the scope block the stop and are sent back to Claude, at most `POLIER_MAX_STOP_REMINDERS` times in a row. |

Requirements: Claude Code, git, Python 3.9+.

## Install

1. Install the package as a Claude Code skill (this also puts the hooks in place):

   ```bash
   git clone https://github.com/atshv/polier.git
   cd polier && ./install.sh claude      # → ~/.claude/skills/polier/
   ```

2. Add the hooks from [`settings.example.json`](settings.example.json) to the
   project's `.claude/settings.json` (or `~/.claude/settings.json` for all
   projects). If you keep the package elsewhere, change the path in both
   commands. Merge the `hooks` block with any hooks you already have.
3. Restart Claude Code, or review the hooks with `/hooks`.

Update with `./update.sh claude`; the hook path stays the same.

## Roles and settings

The hooks read environment variables, so an agent cannot change its own role.
Set them when starting Claude Code (`POLIER_ROLE=lead claude`) or in the `env`
block of a settings file the agent may not edit.

| Variable | Values | Default |
|---|---|---|
| `POLIER_ROLE` | `worker`: only the task scope · `reviewer`: only `reviews/` · `lead`, `off`: no limit | `worker` |
| `POLIER_TASK` | bind the session to one task ID (several tasks `in_progress`) | unset |
| `POLIER_ENFORCE` | `deny` · `ask` (ask the human instead) · `off` | `deny` |
| `POLIER_STOP_CHECK` | `1` · `0` | `1` |
| `POLIER_MAX_STOP_REMINDERS` | integer | `2` |
| `POLIER_BASH` | `1` · `0` (check `Bash` commands) | `1` |

Which tasks bind a session: `POLIER_TASK`, else the `in_progress` task whose
`worktree` contains the session directory, else every `in_progress` task. No
board, no running task or a lead session: the hooks stay out of the way.

Bash specifics: deleting a file git does not track is allowed (it undoes a
write); writes outside the project to `/tmp`, the system temp folder or `/dev`
are not checked. The stop counter lives in `.git/polier/`, outside the working
tree.

## Tests

```bash
python3 -m unittest discover -s adapters/claude-code/tests
```

The tests feed simulated hook events to the hooks, in process and through the
script with JSON on stdin, on throwaway git projects.
