"""Reading board.json and choosing the tasks whose scope applies."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional, Tuple

from .errors import PolierError

BOARD = "board.json"


def find_root(start) -> Optional[Path]:
    """The nearest folder at or above `start` that holds a board.json, or None."""
    if not start:
        return None
    folder = Path(os.path.abspath(str(start)))
    for candidate in (folder, *folder.parents):
        if (candidate / BOARD).exists():
            return candidate
    return None


def load_board(root, strict: bool = True) -> Optional[dict]:
    """Parsed board.json of `root`.

    strict=True raises PolierError for a missing or invalid board (the CLI tools);
    strict=False returns None instead, so a guard stays out of the way.
    """
    path = Path(root) / BOARD
    try:
        board = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        if not strict:
            return None
        raise PolierError(f"board.json not found in {root}") from exc
    except (ValueError, OSError) as exc:
        if not strict:
            return None
        raise PolierError(f"board.json is invalid: {exc}") from exc
    if not isinstance(board, dict) or not isinstance(board.get("tasks"), list):
        if not strict:
            return None
        raise PolierError("board.json has no task list")
    return board


def tasks_of(board: Optional[dict]) -> List[dict]:
    tasks = (board or {}).get("tasks") or []
    return [t for t in tasks if isinstance(t, dict)]


def pick_task(board: dict, task_id: Optional[str] = None) -> dict:
    """The task `task_id`, or the one task in_progress; PolierError otherwise."""
    tasks = tasks_of(board)
    if task_id:
        for task in tasks:
            if task.get("id") == task_id:
                return task
        raise PolierError(f"task {task_id} is not on the board")
    running = [t for t in tasks if t.get("status") == "in_progress"]
    if len(running) == 1:
        return running[0]
    if not running:
        raise PolierError("no task is in_progress; pass --task <ID>")
    ids = ", ".join(str(t.get("id")) for t in running)
    raise PolierError(f"several tasks are in_progress ({ids}); pass --task <ID>")


def active_tasks(board: Optional[dict], root=None, cwd=None, pinned: Optional[str] = None) -> Tuple[List[dict], str]:
    """The tasks whose scope applies to a session, and how they were chosen.

    Order: the pinned task, the in_progress task whose `worktree` contains `cwd`,
    every in_progress task. `how` is pinned, worktree, single, several or none.
    """
    tasks = tasks_of(board)
    if pinned:
        for task in tasks:
            if task.get("id") == pinned:
                return [task], "pinned"
    running = [t for t in tasks if t.get("status") == "in_progress"]
    if not running:
        return [], "none"
    if cwd and root:
        here = os.path.abspath(str(cwd))
        by_tree = []
        for task in running:
            tree = task.get("worktree")
            if not isinstance(tree, str) or not tree:
                continue
            tree = os.path.abspath(os.path.join(str(root), tree))
            if here == tree or here.startswith(tree + os.sep):
                by_tree.append(task)
        if len(by_tree) == 1:
            return by_tree, "worktree"
    return running, "single" if len(running) == 1 else "several"


def ready_tasks(board: Optional[dict]) -> List[dict]:
    """Pending tasks whose dependencies are all done, with their dependencies' handoff notes."""
    tasks = tasks_of(board)
    done = {t.get("id") for t in tasks if t.get("status") == "done"}
    by_id = {t.get("id"): t for t in tasks}
    out = []
    for task in tasks:
        deps = task.get("depends_on") or []
        if task.get("status") != "pending" or not all(d in done for d in deps):
            continue
        out.append({
            "id": task.get("id"),
            "title": task.get("title"),
            "brief": f"tasks/{task.get('id')}.md",
            "handoff": [f"{d}: {h}" for d in deps for h in (by_id.get(d, {}).get("handoff") or [])],
        })
    return out
