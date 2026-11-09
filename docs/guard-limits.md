# What the write guard does not cover

Polier's guard keeps honest agents on track; it is not a sandbox. These are the known gaps.

- **Approvals are cooperative evidence, not authentication.** `reviews/approvals/AP-NNN.json` has no signature and no identity check. Whoever can write the file can forge a granted record, and a shell write is outside the guard. Commit the approval and review it like code.
- **Run records can be forged.** `runs/<ID>.json` is a text file that a hand edit or a shell write can change as easily as the tools; `tools/audit.py` compares it with the board and the evidence folder, not with what happened. A `done` task whose run record was edited is only visible as a contradiction.
- **Command matching is static.** The policy's denied and lead-only patterns are matched against shell segments after quotes, heredocs, assignments and wrappers are stripped, so `git push` is caught. A command assembled by a variable, `eval`, an interpreter or a script file is not.
- **The policy is a file.** Whoever can write `policy.json` can widen the rules. Protect it like the board and review changes to it; the guard reads it, it does not own it.
- **Shell writes it cannot see.** DeepSeek Harness checks only its file tools (`write`, `edit`, `str_replace_editor`) before a write. Everything `bash` writes — redirections, interpreters, build tools, git commands — reaches only the stop check.
- **The stop check sees only `git status`.** Committed changes, ignored files (`.gitignore`, `.git/info/exclude`) and files outside the repository are invisible. It gives up after `maxStopReminders` reminders, and it does not run with several tasks in progress, for lead or reviewer sessions, without git, or when it fails.
- **The board is read on every call.** A shell write the guard cannot see can change `board.json` (task status, `scope_write`) and so widen or switch off the guard. The stop check lists changed records (`board.json`, `STATUS.md`, `factory.json`, `runs/`) but does not count them against the worker, because the lead's tools change them while a task runs; `tools/audit.py` shows a status that the run record does not support.
- **The stop check starts from a snapshot.** Files that were already changed when the worker bound the task (`pl_task`) are skipped while they stay unchanged.
- **Paths are compared as text.** Symlinks are not followed, so a link inside the scope can point outside it. The comparison ignores case on macOS and Windows, where the file system does, but two different spellings on a case-sensitive file system are two different paths. Protected-path patterns use the same comparison.
- **The project is found from the session folder.** A session that starts outside the project, or in a worktree whose `board.json` still shows the task as `pending`, is not guarded until it is bound to a task with `pl_task`.
- **Claims are cooperative.** A live claim stops a second session that uses the claim tools and names the holder; a session that never claims is not stopped by a claim alone. A claim is not a lock on files.
- **Gate records can be forged.** `reviews/evidence/` is always writable, and an agent can write a log and a matching record itself; the gate command is free text. A reviewer must compare the recorded command with `AGENTS.md`.
- **Writes fail closed, commands fail open.** If `tools/guard.py` cannot answer (Python missing, a crash), a guarded write is blocked with the reason and a `bash` command goes through. Roles live in memory; switching to lead or off needs an approval prompt, but whoever can edit the plugin config can set `enforce: off`.
- **Each guarded call costs one short Python process.** A write or a `bash` command inside a Polier project waits for `tools/guard.py` to answer (typically well under a second).
- **The kill warning is advisory.** `kill`, `pkill` and `killall` never block a command; the plugin sends one message per turn. A sandbox is the only real protection against stopping another session's processes.
- **Approval prompts need an answerer.** Without one (headless runs, `policy: never`) every prompt fails closed: no lead mode, no closed station, no granted approval. Use the `tools/*.py` commands as the owner there.
- **Other plugins and MCP servers extend what an agent can reach.** Their tools run with their own permissions, outside the write guard. Give agents only what their task needs.

For hard limits, run workers in a sandbox or a container with write access to the task's files only.
