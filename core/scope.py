"""Write scopes: may a session write a path (guard), and do the changed files fit (stop check)?

Two entry points with deliberately different rules, kept as they shipped:

- check_write() decides one write before it happens. Evidence and lead-owned
  files are checked before scope_write_forbidden, and with several running
  tasks a path must fit one of them. The DSH plugin mirrors it in
  adapters/dsh/lib/project.mjs; core/tests/write_cases.json keeps the two in step.
- check_stop() looks at every changed file of one task after the fact.
  scope_write_forbidden wins over everything, board files pass with allow_board.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable, List, NamedTuple, Optional, Tuple, Union

from .board import load_board, pick_task
from .errors import PolierError
from .paths import inside, normalized, outside, relative, resolve

# Always writable: gate logs and records belong to the task that produced them.
ALWAYS_ALLOWED = ("reviews/evidence",)
# Lead-owned files: a worker must not edit the board, the generated status or briefs.
BOARD_FILES = ("board.json", "STATUS.md", "tasks")
# The only folder a reviewer session writes to.
REVIEWS = "reviews"
# Session roles: worker (default) is limited to the task scope, reviewer to reviews/,
# lead and off are not limited.
ROLES = ("worker", "reviewer", "lead", "off")


class Decision(NamedTuple):
    ok: bool
    code: str = ""
    reason: str = ""
    path: str = ""


def _strings(task: dict, key: str) -> List[str]:
    value = task.get(key)
    return [p for p in value if isinstance(p, str)] if isinstance(value, list) else []


# ---------------------------------------------------------------------------
# guard: one write, before it happens
# ---------------------------------------------------------------------------

def decide(rel: str, tasks: Iterable[dict]) -> Decision:
    """May a worker write `rel` (relative to the project root)? With several tasks it must fit one."""
    if outside(rel):
        return Decision(False, "outside-project", "is outside the project folder", rel)
    if any(inside(rel, a) for a in ALWAYS_ALLOWED):
        return Decision(True, path=rel)
    if any(inside(rel, b) for b in BOARD_FILES):
        return Decision(False, "lead-owned", "is lead-owned (board, status or brief)", rel)
    forbidden = False
    for task in tasks:
        if any(inside(rel, d) for d in _strings(task, "scope_write_forbidden")):
            forbidden = True
            continue
        if any(inside(rel, a) for a in _strings(task, "scope_write")):
            return Decision(True, path=rel)
    if forbidden:
        return Decision(False, "forbidden", "is listed in scope_write_forbidden", rel)
    return Decision(False, "outside-scope", "is outside the write scope", rel)


def check_write(path: str, tasks: Union[dict, Iterable[dict], None], role: str = "worker",
                root=None, cwd=None) -> Decision:
    """Guard decision for writing `path`.

    `tasks` is the task (or list of tasks) bound to the session; empty means no
    task is running and a worker may write anything. With `root`, `path` may be
    absolute or relative to `cwd` (default: `root`); without it, `path` must
    already be relative to the project root.
    """
    if isinstance(tasks, dict):
        tasks = [tasks]
    tasks = [t for t in (tasks or []) if isinstance(t, dict)]
    rel = relative(root, resolve(cwd or root, path)) if root is not None else normalized(path)
    if role == "reviewer":
        if inside(rel, REVIEWS) and not rel.startswith("../"):
            return Decision(True, path=rel)
        return Decision(False, "reviewer", "is outside reviews/", rel)
    if role != "worker" or not tasks:
        return Decision(True, path=rel)
    return decide(rel, tasks)


def write_denial(decision: Decision, tasks: Union[dict, Iterable[dict], None], role: str = "worker",
                 target: str = "") -> str:
    """The message an agent gets for a denied write."""
    shown = decision.path or target
    if role == "reviewer":
        return (f"Polier: write to {shown} blocked, a reviewer session writes only under reviews/. "
                "Report the problem in the review instead of fixing it.")
    if isinstance(tasks, dict):
        tasks = [tasks]
    tasks = [t for t in (tasks or []) if isinstance(t, dict)]
    ids = ", ".join(str(t.get("id")) for t in tasks)
    allowed: List[str] = []
    for task in tasks:
        for entry in task.get("scope_write") or []:
            if entry not in allowed:
                allowed.append(entry)
    return " ".join([
        f"Polier: write to {shown} blocked, the path {decision.reason} of {ids}.",
        f"Allowed: {', '.join(allowed) or 'nothing'}.",
        "Do not try another way to write it. If the change is needed, stop and report it under open_questions.",
    ])


# ---------------------------------------------------------------------------
# stop check: every changed file, after the fact
# ---------------------------------------------------------------------------

def changed_files(root) -> List[str]:
    """All changed paths relative to `root`, in git's order: modified, staged,
    untracked, deleted and both sides of a rename. Ignored files are not counted."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1", "-z", "-uall"],
            capture_output=True, check=False,
        )
    except FileNotFoundError as exc:
        raise PolierError("git not found") from exc
    if result.returncode != 0:
        raise PolierError(f"not a git repository: {root}")

    prefix = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-prefix"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()

    fields = result.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    paths: List[str] = []
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        paths.append(path)
        if "R" in status or "C" in status:  # rename/copy: the old path follows
            if i < len(fields) and fields[i]:
                paths.append(fields[i])
            i += 1

    # git reports paths relative to the repository root; make them relative to the project.
    out: List[str] = []
    for path in paths:
        rel = normalized(path)
        if prefix:
            pre = normalized(prefix)
            rel = rel[len(pre) + 1:] if rel.startswith(pre + "/") else "../" + rel
        if rel not in out:
            out.append(rel)
    return out


def is_tracked(root, rel: str) -> bool:
    """True if git tracks `rel` or any file below it. Deleting an untracked file
    undoes a write, so guards let it through."""
    try:
        result = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", rel or "."],
                                capture_output=True, check=False)
    except FileNotFoundError:
        return True
    return result.returncode != 0 or bool(result.stdout.strip(b"\0"))


def violations(paths: Iterable[str], task: dict, allow_board: bool = False) -> List[Tuple[str, str]]:
    """(path, reason) for every path outside the task's scope."""
    allowed = [p for p in task.get("scope_write", []) if isinstance(p, str)]
    forbidden = [p for p in task.get("scope_write_forbidden", []) if isinstance(p, str)]
    found: List[Tuple[str, str]] = []
    for path in paths:
        if path.startswith("../") or path == "..":
            found.append((path, "outside the project"))
        elif any(inside(path, f) for f in forbidden):
            found.append((path, "forbidden"))
        elif any(inside(path, a) for a in ALWAYS_ALLOWED):
            continue
        elif any(inside(path, b) for b in BOARD_FILES):
            if not allow_board:
                found.append((path, "lead-owned (board, status or brief)"))
        elif not any(inside(path, a) for a in allowed):
            found.append((path, "outside scope"))
    return found


def check_stop(changed: List[str], task: dict, allow_board: bool = False) -> dict:
    """Compare changed files (project-relative) with one task's scope."""
    found = violations(changed, task, allow_board)
    return {
        "task": task.get("id"),
        "ok": not found,
        "changed": list(changed),
        "violations": [{"path": p, "reason": r} for p, r in found],
        "scope_write": task.get("scope_write", []),
    }


def scope_check(root, task_id: Optional[str] = None, allow_board: bool = False) -> dict:
    """Board, task and git status of `root` in one call; raises PolierError on environment problems."""
    root = Path(root)
    board = load_board(root)
    task = pick_task(board, task_id)
    return check_stop(changed_files(root), task, allow_board)


def stop_message(task: dict, found: List[dict]) -> str:
    """The message an agent gets when its turn ends with changes outside the scope."""
    lines = [f"- {v.get('path')}: {v.get('reason')}" for v in found[:20]]
    return "\n".join([
        f"Polier: the working tree has changes outside the scope of {task.get('id')}.",
        *lines,
        f"Allowed: {', '.join(task.get('scope_write') or []) or 'nothing'}.",
        "Undo these changes (git checkout/rm for files you created or edited), or, if they are needed,",
        "keep them and report each one under open_questions in your result. Then finish.",
    ])
