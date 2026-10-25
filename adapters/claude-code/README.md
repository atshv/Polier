# Claude Code adapter

Hooks that apply Polier's write guard and stop check in Claude Code. They call
only [`core/`](../../core/); the rules are the same as in the DeepSeek Harness
plugin.

| Hook | Event | Effect |
|---|---|---|
| `hook.py pre-tool-use` | `PreToolUse` on `Write`, `Edit`, `MultiEdit`, `NotebookEdit`, `Bash` | A write outside the running task's scope is denied with the reason. For `Bash`, the files the command visibly writes are checked (redirections, `tee`, `cp`/`mv`, `rm`, `sed -i`, …; see [`core/shell.py`](../../core/shell.py)). With `POLIER_TASK` the hook takes/refreshes that task's claim and denies the write when another live session holds the task. A task with a worktree is denied in the main checkout ("work in <worktree path>"). A `Bash` command that stops processes (`kill`, `pkill`, `killall`, `xargs kill`) gets an `ask` — never a denial. |
| `hook.py stop` | `Stop` | Changed files (`git status`) outside the scope block the stop and are sent back to Claude, at most `POLIER_MAX_STOP_REMINDERS` times in a row. Changed files inside another live claim's scope are reported as "foreign changes (task X, harness Y)" and never block. |

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
3. Commit `.claude/settings.json`; otherwise the stop check reports it as a change outside the task scope.
4. Restart Claude Code, or review the hooks with `/hooks`.

Update with `./update.sh claude`; the hook path stays the same. One update is
needed to get `tools/manifest.json`, which `check.py` uses for drift detection.

## Roles and settings

The hooks read environment variables, so an agent cannot change its own role.
Set them when starting Claude Code (`POLIER_ROLE=lead claude`) or in the `env`
block of a settings file the agent may not edit.

| Variable | Values | Default |
|---|---|---|
| `POLIER_ROLE` | `worker`: only the task scope · `reviewer`: only `reviews/` · `lead`, `off`: no limit | `worker` |
| `POLIER_TASK` | bind the session to one task ID and claim it (several tasks `in_progress`) | unset |
| `POLIER_ENFORCE` | `deny` · `ask` (ask the human instead) · `off` | `deny` |
| `POLIER_STOP_CHECK` | `1` · `0` | `1` |
| `POLIER_MAX_STOP_REMINDERS` | integer | `2` |
| `POLIER_BASH` | `1` · `0` (check `Bash` commands) | `1` |

Which tasks bind a session: `POLIER_TASK`, else the `in_progress` task whose
`worktree` contains the session directory, else every `in_progress` task. No
board, no running task or a lead session: the hooks stay out of the way.

## Claims

With `POLIER_TASK` set, every `PreToolUse` takes or refreshes the claim in
`<git-common-dir>/polier/claims/<task>.json` (harness `claude-code`, the session
id from the hook event, the worktree and the slot from `.polier-slot`). A live
claim of another session — DeepSeek Harness or Claude Code — denies the write
and names the holder, so two sessions cannot work on one task. The hook has no
session-end event: a claim goes stale after 10 minutes without a tool call and
the session's next call takes it again. `tools/claim.py list` shows every live
claim of the repo.

The claim is best effort outside git; without a repository the guard still runs
and no claim is written.

## Worktrees, slots and foreign changes

- The board's `worktrees: required` (default at M/L) denies a writer in the
  main checkout while the task has a `worktree`; start the session inside the
  worktree, with `POLIER_TASK` set, and Claude Code guards it there.
- Ports, database and bucket names come from `.polier-slot` in the session
  folder; the hook only uses the slot number for the claim. Create the worktree
  with `tools/worktree.py start <ID>` (or `git worktree add` +
  `tools/slot.py acquire`) before a worker session starts.
- The stop check lists changes made by another live claim as foreign changes and
  does not block for them; the current task's violations still block.

Bash specifics: deleting a file git does not track is allowed (it undoes a
write); writes outside the project to `/tmp`, the system temp folder or `/dev`
are not checked. The stop counter lives under the worktree's own git path
(`.git/polier/` in the main checkout), outside the working tree. The kill
warning is advisory: `ask` shows the command to you.

What the hooks do not cover is listed in the main [README](../../README.md#what-the-guard-does-not-cover).

## Tests

```bash
python3 -m unittest discover -s adapters/claude-code/tests
```

The tests feed simulated hook events to the hooks, in process and through the
script with JSON on stdin, on throwaway git projects: scope denials, Bash writes,
claims and claim conflicts, worktree denials, kill warnings, the stop check and
foreign changes.
