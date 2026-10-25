#!/usr/bin/env python3
"""Create and finish a task worktree: branch, runtime slot and claim in one step (PL-05).

Usage:
    python3 tools/worktree.py start M03 [--root .] [--base main] [--session S] [--harness cli]
    python3 tools/worktree.py finish M03 [--root .]

start:
    1. `git worktree add ../<repo>-<task> -b task/<task> <base>` (from the main checkout)
    2. `core.slots.acquire` (tools/slot.py logic), which writes .polier-slot
    3. `core.claims.take <task> --harness ... --session ... --worktree <path> --slot <N>`
    4. sets `worktree` on that task in board.json (only that field) and prints the path

finish:
    refuses (exit 1, changes nothing) while `git status --porcelain` in the
    worktree is non-empty; otherwise releases the claim and the slot, removes
    the worktree and clears `worktree` on the task.

Exit codes: 0 done, 1 refused (dirty worktree, live claim of another session,
task without worktree), 2 usage or environment error (not a git repository,
invalid board, git or slot failure). English output. No external dependencies.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.board import load_board  # noqa: E402
from core.claims import ClaimConflict, release, take  # noqa: E402
from core.errors import PolierError  # noqa: E402
from core.paths import main_checkout  # noqa: E402

BOARD = "board.json"
SLOT_FILE = ".polier-slot"


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _git(folder, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", str(folder), *args],
                              capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return subprocess.CompletedProcess(["git", *args], 127, "", "git not found")


def _slot_number(folder) -> Optional[int]:
    """The slot integer from `.polier-slot` in `folder`, or None."""
    try:
        data = json.loads((Path(folder) / SLOT_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("N", data.get("slot"))
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _slot_module():
    try:
        from core import slots
    except ImportError:  # PL-02 not installed yet
        return None
    return slots


def _acquire_slot(worktree: Path) -> Optional[int]:
    """Take the worktree's runtime slot with core.slots.acquire; None without PL-02."""
    slots = _slot_module()
    if slots is None:
        print("WORKTREE: slot module not found (PL-02 is not installed); continuing without a slot",
              file=sys.stderr)
        return None
    try:
        data = slots.acquire(worktree)
    except PolierError as exc:
        raise PolierError(f"slot.py acquire failed: {exc}") from exc
    value = data.get("slot") if isinstance(data, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _release_slot(worktree: Path) -> None:
    """Release the worktree's slot (best effort)."""
    slots = _slot_module()
    if slots is None:
        return
    try:
        slots.release(worktree)
    except PolierError as exc:
        print(f"WORKTREE WARNING: slot.py release failed: {exc}", file=sys.stderr)


def _board_of(main: Path, root: Path) -> Optional[dict]:
    for folder in (main, root):
        board = load_board(folder, strict=False)
        if board is not None:
            return board
    return None


def _find_task(board: dict, task_id: str) -> dict:
    for task in board.get("tasks") or []:
        if isinstance(task, dict) and task.get("id") == task_id:
            return task
    raise PolierError(f"task {task_id} is not on the board")


def set_worktree(main: Path, task_id: str, value: Optional[str]) -> None:
    """Set only `worktree` of one task in board.json (lead action)."""
    path = Path(main) / BOARD
    try:
        board = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PolierError(f"cannot read {path}: {exc}") from exc
    found = False
    for task in board.get("tasks") or []:
        if isinstance(task, dict) and task.get("id") == task_id:
            task["worktree"] = value
            found = True
    if not found:
        raise PolierError(f"task {task_id} is not on the board")
    path.write_text(json.dumps(board, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _worktree_dir(main: Path, task_id: str) -> Path:
    return main.parent / f"{main.name}-{task_id}"


def _stored_worktree(main: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (main / path)


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------

def start(root, task_id: str, base: str = "main", session: Optional[str] = None,
          harness: str = "cli") -> int:
    root = Path(root)
    try:
        main = main_checkout(root)
    except PolierError as exc:
        print(f"WORKTREE ERROR: {exc}", file=sys.stderr)
        return 2
    board = _board_of(main, root)
    if board is None:
        print(f"WORKTREE ERROR: board.json not found in {main} or {root}", file=sys.stderr)
        return 2
    try:
        task = _find_task(board, task_id)
    except PolierError as exc:
        print(f"WORKTREE ERROR: {exc}", file=sys.stderr)
        return 2
    if task.get("worktree"):
        print(f"WORKTREE ERROR: task {task_id} already has a worktree: {task['worktree']}", file=sys.stderr)
        return 1

    target = _worktree_dir(main, task_id)
    branch = f"task/{task_id}"
    if target.exists():
        print(f"WORKTREE ERROR: target folder already exists: {target}", file=sys.stderr)
        return 2
    if _git(main, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}").returncode == 0:
        print(f"WORKTREE ERROR: branch {branch} already exists", file=sys.stderr)
        return 2

    added = _git(main, "worktree", "add", str(target), "-b", branch, base)
    if added.returncode != 0:
        print(f"WORKTREE ERROR: git worktree add failed: {added.stderr.strip() or added.stdout.strip()}",
              file=sys.stderr)
        return 2

    try:
        slot = _acquire_slot(target)
    except PolierError as exc:
        print(f"WORKTREE ERROR: {exc}", file=sys.stderr)
        _git(main, "worktree", "remove", "--force", str(target))
        _git(main, "branch", "-D", branch)
        return 1
    slot = _slot_number(target) if slot is None else slot

    session = session or f"cli-{os.getpid()}"
    try:
        take(main, task_id, harness=harness, session=session, worktree=str(target), slot=slot)
    except ClaimConflict as exc:
        print(f"WORKTREE ERROR: {exc}", file=sys.stderr)
        _git(main, "worktree", "remove", "--force", str(target))
        _git(main, "branch", "-D", branch)
        _release_slot(target)
        return 1
    except PolierError as exc:
        print(f"WORKTREE ERROR: {exc}", file=sys.stderr)
        _git(main, "worktree", "remove", "--force", str(target))
        _git(main, "branch", "-D", branch)
        _release_slot(target)
        return 2

    try:
        set_worktree(main, task_id, os.path.relpath(str(target), str(main)).replace(os.sep, "/"))
    except (PolierError, OSError) as exc:
        print(f"WORKTREE ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"WORKTREE {task_id}: branch {branch} from {base}, slot "
          f"{slot if slot is not None else '-'}, session {session}", file=sys.stderr)
    print(target)
    return 0


# ---------------------------------------------------------------------------
# finish
# ---------------------------------------------------------------------------

def finish(root, task_id: str) -> int:
    root = Path(root)
    try:
        main = main_checkout(root)
    except PolierError as exc:
        print(f"WORKTREE ERROR: {exc}", file=sys.stderr)
        return 2
    board = _board_of(main, root)
    if board is None:
        print(f"WORKTREE ERROR: board.json not found in {main} or {root}", file=sys.stderr)
        return 2
    try:
        task = _find_task(board, task_id)
    except PolierError as exc:
        print(f"WORKTREE ERROR: {exc}", file=sys.stderr)
        return 2
    value = task.get("worktree")
    if not isinstance(value, str) or not value.strip():
        print(f"WORKTREE ERROR: task {task_id} has no worktree", file=sys.stderr)
        return 1
    worktree = _stored_worktree(main, value)
    if not worktree.exists():
        print(f"WORKTREE ERROR: worktree folder not found: {worktree}", file=sys.stderr)
        return 1

    status = _git(worktree, "status", "--porcelain")
    if status.returncode != 0:
        print(f"WORKTREE ERROR: not a git worktree: {worktree}", file=sys.stderr)
        return 2
    dirty: List[str] = [line for line in status.stdout.splitlines()
                        if line.strip() and line[3:].strip() != SLOT_FILE]
    if dirty:
        print(f"WORKTREE REFUSED: {task_id} has uncommitted changes in {worktree}; nothing was removed.",
              file=sys.stderr)
        for line in dirty[:20]:
            print(f"  {line}", file=sys.stderr)
        if len(dirty) > 20:
            print(f"  ... and {len(dirty) - 20} more", file=sys.stderr)
        return 1

    released = release(main, task_id)
    _release_slot(worktree)

    removed = _git(main, "worktree", "remove", str(worktree))
    if removed.returncode != 0:
        print(f"WORKTREE ERROR: git worktree remove failed: "
              f"{removed.stderr.strip() or removed.stdout.strip()}", file=sys.stderr)
        return 1

    try:
        set_worktree(main, task_id, None)
    except (PolierError, OSError) as exc:
        print(f"WORKTREE ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"WORKTREE REMOVED {task_id}: {worktree} (claim released: {'yes' if released else 'none'})")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    start_p = sub.add_parser("start", help="create worktree + branch, acquire a slot and claim the task")
    start_p.add_argument("task", help="task ID, e.g. M03")
    start_p.add_argument("--root", default=".", help="project folder (default: .)")
    start_p.add_argument("--base", default="main", help="base branch for the task branch (default: main)")
    start_p.add_argument("--session", help="claim session id (default: cli-<pid>)")
    start_p.add_argument("--harness", default="cli", choices=("dsh", "claude-code", "cli"),
                         help="harness that holds the claim (default: cli)")

    finish_p = sub.add_parser("finish", help="release claim and slot, remove a clean worktree")
    finish_p.add_argument("task", help="task ID")
    finish_p.add_argument("--root", default=".", help="project folder (default: .)")

    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            return start(args.root, args.task, base=args.base, session=args.session, harness=args.harness)
        return finish(args.root, args.task)
    except PolierError as exc:
        print(f"WORKTREE ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"WORKTREE ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
