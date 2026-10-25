#!/usr/bin/env python3
"""Claude Code hooks for Polier.

Usage, from .claude/settings.json (see settings.example.json):
    python3 <package>/adapters/claude-code/hook.py pre-tool-use
    python3 <package>/adapters/claude-code/hook.py stop

Reads the hook event as JSON on stdin and answers in Claude Code's hook format:
- pre-tool-use: Write, Edit, MultiEdit, NotebookEdit and the writes core/shell.py
  finds in a Bash command are checked with core.scope.check_write; a denial
  (or, with POLIER_ENFORCE=ask, a question to the human) goes to stdout as JSON.
  With POLIER_TASK the hook takes/refreshes that task's claim (PL-04) and denies
  a write when another live session holds it; a Bash command that stops
  processes gets an "ask" warning (PL-16).
- stop: the git diff is compared with the running task (core.scope.check_stop);
  violations block the stop once per reminder, at most POLIER_MAX_STOP_REMINDERS
  times in a row. Changed files inside another live claim's scope are listed as
  foreign changes and never block (PL-05).

Settings come from the environment, which the agent cannot change for the hook:
    POLIER_ROLE                 worker (default) | reviewer | lead | off
    POLIER_TASK                 bind the session to one task ID
    POLIER_ENFORCE              deny (default) | ask | off
    POLIER_STOP_CHECK           1 (default) | 0
    POLIER_MAX_STOP_REMINDERS   2 (default)
    POLIER_BASH                 1 (default) | 0: check Bash commands too

Any internal error lets the call through (exit 0, note on stderr): the hook
never blocks work because of its own failure. No external dependencies.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Mapping, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.board import active_tasks, find_root, load_board  # noqa: E402
from core.claims import ClaimConflict, take as claim_take  # noqa: E402
from core.errors import PolierError  # noqa: E402
from core.paths import inside, outside, relative  # noqa: E402
from core.scope import ROLES, changed_files, check_stop, check_write, is_tracked, stop_message, write_denial  # noqa: E402
from core.shell import process_kills, write_targets  # noqa: E402

# Claude Code tools that write one file, with the input field that holds its path.
FILE_TOOLS = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
# Bash targets outside the project that are scratch space, not someone else's files.
SCRATCH = ("/dev", tempfile.gettempdir(), "/tmp")
# Advisory only: stopping processes is not a write and must never be a denial (PL-16).
KILL_WARNING = "Polier: do not stop processes you did not start; use your slot's ports."
SLOT_FILE = ".polier-slot"


def settings(env: Mapping[str, str]) -> dict:
    role = env.get("POLIER_ROLE", "worker").strip().lower()
    enforce = env.get("POLIER_ENFORCE", "deny").strip().lower()
    try:
        reminders = max(0, int(env.get("POLIER_MAX_STOP_REMINDERS", "2")))
    except ValueError:
        reminders = 2
    return {
        "role": role if role in ROLES else "worker",
        "task": env.get("POLIER_TASK", "").strip().upper() or None,
        "enforce": enforce if enforce in ("deny", "ask", "off") else "deny",
        "stop_check": env.get("POLIER_STOP_CHECK", "1").strip() not in ("0", "false", "no", "off"),
        "max_reminders": reminders,
        "bash": env.get("POLIER_BASH", "1").strip() not in ("0", "false", "no", "off"),
    }


def session(event: dict, env: Mapping[str, str]) -> Optional[dict]:
    """Project root, board and bound tasks; None when no board is found."""
    cwd = event.get("cwd") or env.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    root = find_root(cwd) or find_root(env.get("CLAUDE_PROJECT_DIR"))
    if root is None:
        return None
    board = load_board(root, strict=False)
    if board is None:
        return None
    cfg = settings(env)
    tasks, how = active_tasks(board, root=root, cwd=cwd, pinned=cfg["task"])
    return {"cwd": cwd, "root": root, "board": board, "tasks": tasks, "how": how, **cfg}


# ---------------------------------------------------------------------------
# PreToolUse
# ---------------------------------------------------------------------------

def _scratch(path: str) -> bool:
    return any(inside(path, s) for s in SCRATCH)


def _slot(folder) -> Optional[int]:
    """The slot integer from `.polier-slot`, or None (PL-02 writes it)."""
    try:
        data = json.loads((Path(folder) / SLOT_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = data.get("N", data.get("slot")) if isinstance(data, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _claim_reason(info: dict, event: dict) -> Optional[str]:
    """Take/refresh the claim of POLIER_TASK; a denial naming the holder when another session has it."""
    task_id = info.get("task")
    if not task_id or info.get("role") != "worker":
        return None
    session_id = str(event.get("session_id") or "").strip() or "claude-code"
    try:
        claim_take(info["root"], task_id, harness="claude-code", session=session_id,
                   worktree=str(info["cwd"]), slot=_slot(info["cwd"]))
    except ClaimConflict as exc:
        return f"Polier: write blocked, {exc}. Another session works on this task."
    except PolierError:  # no git repository yet: the claim is best effort, the guard still runs
        return None
    return None


def _output(info: dict, reason: str, decision: Optional[str] = None) -> dict:
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision or ("ask" if info["enforce"] == "ask" else "deny"),
        "permissionDecisionReason": reason,
    }}


def _bash_denial(info: dict, command: str) -> Optional[str]:
    targets, _unresolved = write_targets(command, info["cwd"])
    for target in targets:
        rel = relative(info["root"], target.path)
        if outside(rel) and _scratch(target.path):
            continue
        decision = check_write(target.path, info["tasks"], role=info["role"], root=info["root"],
                               board=info["board"])
        if decision.ok:
            continue
        if target.how == "delete" and not outside(rel) and not is_tracked(info["root"], rel):
            continue  # removing an untracked file undoes a write
        return f"{write_denial(decision, info['tasks'], info['role'], target.path)} (Bash: {target.command})"
    return None


def pre_tool_use(event: dict, env: Mapping[str, str]) -> Optional[dict]:
    name = event.get("tool_name")
    args = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    if name not in FILE_TOOLS and name != "Bash":
        return None
    cfg = settings(env)
    if cfg["enforce"] == "off":
        return None
    info = session(event, env)
    if info is None:
        return None

    # PL-04: with POLIER_TASK this session owns the claim; another live session
    # of any harness blocks the write and is named in the reason.
    claim_reason = _claim_reason(info, event)
    if claim_reason is not None:
        return _output(info, claim_reason)

    command = args.get("command") if name == "Bash" else None
    reason: Optional[str] = None
    if name == "Bash":
        if cfg["bash"] and isinstance(command, str) and command:
            reason = _bash_denial(info, command)
    else:
        target = args.get(FILE_TOOLS[name])
        if not isinstance(target, str) or not target:
            return None
        decision = check_write(target, info["tasks"], role=info["role"], root=info["root"],
                               cwd=info["cwd"], board=info["board"])
        reason = None if decision.ok else write_denial(decision, info["tasks"], info["role"], target)
    if reason is not None:  # a real write violation wins over the advisory kill warning
        return _output(info, reason)

    # PL-16: a Bash command that stops processes gets a question, never a denial.
    if name == "Bash" and info["role"] == "worker" and isinstance(command, str) and command:
        if process_kills(command):
            return _output(info, KILL_WARNING, decision="ask")
    return None


# ---------------------------------------------------------------------------
# Stop
# ---------------------------------------------------------------------------

def _counter_file(root: Path, session_id: str) -> Optional[Path]:
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "--git-path", "polier"],
                            capture_output=True, text=True, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    folder = Path(result.stdout.strip())
    folder = folder if folder.is_absolute() else root / folder
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "default")
    return folder / f"claude-code-stop-{safe}.json"


def _read_count(path: Optional[Path]) -> int:
    try:
        return int(json.loads(path.read_text(encoding="utf-8")).get("count", 0)) if path else 0
    except (OSError, ValueError, AttributeError):
        return 0


def _write_count(path: Optional[Path], count: int) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"count": count}), encoding="utf-8")
    except OSError:
        pass


def stop(event: dict, env: Mapping[str, str]) -> Optional[dict]:
    cfg = settings(env)
    if not cfg["stop_check"]:
        return None
    info = session(event, env)
    if info is None or info["role"] != "worker" or len(info["tasks"]) != 1:
        return None
    task = info["tasks"][0]
    counter = _counter_file(info["root"], str(event.get("session_id") or ""))
    # A stop that Claude Code did not cause by an earlier block starts a new count.
    count = _read_count(counter) if event.get("stop_hook_active") else 0
    if count >= cfg["max_reminders"]:
        return None
    try:
        result = check_stop(changed_files(info["root"]), task, root=info["root"])
    except PolierError:
        return None
    foreign = result.get("foreign") or []
    foreign_lines = [f"- foreign changes (task {item.get('task')}, harness {item.get('harness')}): "
                     f"{item.get('path')}" for item in foreign]
    if result["ok"]:
        _write_count(counter, 0)
        if foreign_lines:
            # Other live claims changed these files: report them, never block for them.
            return {"systemMessage": "Polier: foreign changes were made by other live claims "
                                     "(not yours):\n" + "\n".join(foreign_lines)}
        return None
    _write_count(counter, count + 1)
    reason = stop_message(task, result["violations"])
    if foreign_lines:
        reason += "\n\nForeign changes (not yours, not blocking):\n" + "\n".join(foreign_lines)
    return {"decision": "block", "reason": reason}


# ---------------------------------------------------------------------------
# entry
# ---------------------------------------------------------------------------

HANDLERS = {"pre-tool-use": pre_tool_use, "stop": stop}


def main(argv=None, stdin=None, env=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    env = os.environ if env is None else env
    if len(argv) != 1 or argv[0] not in HANDLERS:
        print(f"usage: hook.py {' | '.join(HANDLERS)}", file=sys.stderr)
        return 1  # a non-blocking hook error in Claude Code
    try:
        event = json.loads((stdin or sys.stdin).read() or "{}")
        output = HANDLERS[argv[0]](event if isinstance(event, dict) else {}, env)
    except Exception as exc:  # noqa: BLE001  never block work because of the hook itself
        print(f"polier hook: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 0
    if output:
        print(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
