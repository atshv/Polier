"""Write scopes: may a session write a path (guard), and do the changed files fit (stop check)?

Two entry points with deliberately different rules, kept as they shipped:

- check_write() decides one write before it happens. Evidence and lead-owned
  files are checked before scope_write_forbidden, and with several running
  tasks a path must fit one of them.
- check_stop() looks at every changed file of one task after the fact.
  scope_write_forbidden wins over everything, board files pass with allow_board.

Both also lock the scope of a task in verifying or review against workers that
are not bound to it (locked_by).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Iterable, List, NamedTuple, Optional, Tuple, Union

from .board import load_board, pick_task, tasks_of
from .claims import live_claims
from .errors import PolierError
from .paths import git_common_dir, inside, is_main_checkout, normalized, outside, relative, resolve

# Always writable: gate logs and records belong to the task that produced them.
ALWAYS_ALLOWED = ("reviews/evidence",)
# Lead-owned files: a worker must not edit the board, the generated status, the
# briefs or the run records (both are written by the tools).
BOARD_FILES = ("board.json", "STATUS.md", "tasks", "runs")
# Records the Polier tools write (state, line, approvals). In the stop check they
# never count against a worker: the lead's tools change them while a task runs.
RECORDS = ("board.json", "STATUS.md", "STATUS.html", "factory.json", "docs/factory.md",
           "runs", "reviews/approvals")
# Records only the Polier tools write: a worker never writes them with a file tool,
# bound to a task or not (a worker with no task may otherwise write anything).
RECORD_WRITES = ("board.json", "factory.json", "runs", "reviews/approvals")
# The only folder a reviewer session writes to.
REVIEWS = "reviews"
# A task in one of these states is under review: its scope is frozen for workers.
LOCKED_STATUSES = ("verifying", "review")
# Approval records are the approver's: a reviewer writes review material, never
# the approval ledger (tools/approve.py owns it).
APPROVALS = "reviews/approvals"


class Decision(NamedTuple):
    ok: bool
    code: str = ""
    reason: str = ""
    path: str = ""


def _strings(task: dict, key: str) -> List[str]:
    value = task.get(key)
    return [p for p in value if isinstance(p, str)] if isinstance(value, list) else []


def locked_by(rel: str, board, own: Iterable[str] = ()) -> List[Tuple[str, str]]:
    """(task id, status) of every task under review whose `scope_write` holds `rel`.

    Tasks in `own` (the session's bound tasks) are not counted. Evidence paths are never locked.
    """
    if not isinstance(board, dict) or any(inside(rel, a) for a in ALWAYS_ALLOWED):
        return []
    own = set(own)
    return [(t.get("id"), t.get("status")) for t in tasks_of(board)
            if t.get("status") in LOCKED_STATUSES and t.get("id") not in own
            and any(inside(rel, e) for e in _strings(t, "scope_write"))]


def worktree_mode(board) -> str:
    """`worktrees` mode of the board: required, recommended or off.

    Without a valid board setting the profile decides: off for S, required for M/L.
    """
    if not isinstance(board, dict):
        return "off"
    mode = board.get("worktrees")
    if mode in ("required", "recommended", "off"):
        return mode
    if board.get("profile") not in ("M", "L"):
        return "off"
    return "required"


def worktree_denial(tasks: Iterable[dict], board=None, root=None) -> Optional[str]:
    """The task worktree a worker must use instead of the main checkout, or None.

    The rule applies with `worktrees: required` (or its M/L default), a bound
    task that has a non-empty `worktree`, and a session in the main checkout.
    Inside a linked worktree, or without board/root, nothing is denied.
    """
    if root is None or worktree_mode(board) != "required":
        return None
    trees = [t.get("worktree") for t in tasks
             if isinstance(t, dict) and isinstance(t.get("worktree"), str) and t.get("worktree").strip()]
    if not trees:
        return None
    if not is_main_checkout(root):
        return None
    return trees[0]


# ---------------------------------------------------------------------------
# guard: one write, before it happens
# ---------------------------------------------------------------------------

def decide(rel: str, tasks: Iterable[dict], board=None, root=None, cwd=None) -> Decision:
    """May a worker write `rel` (relative to the project root)? With several tasks it must fit one.

    With `board` and `root` the worktree rule of applies as well: a worker
    write in the main checkout while a bound task has a worktree is denied.
    """
    if outside(rel):
        return Decision(False, "outside-project", "is outside the project folder", rel)
    if any(inside(rel, a) for a in ALWAYS_ALLOWED):
        return Decision(True, path=rel)
    if any(inside(rel, b) for b in BOARD_FILES):
        return Decision(False, "lead-owned", "is lead-owned (board, status or brief)", rel)
    tree = worktree_denial(tasks, board, root)
    if tree:
        return Decision(False, "worktree", f"work in {tree}", rel)
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
                root=None, cwd=None, board=None) -> Decision:
    """Guard decision for writing `path`.

    `tasks` is the task (or list of tasks) bound to the session; empty means no
    task is running and a worker may write anything except the scope of a task
    in `verifying` or `review`. With `root`, `path` may be
    absolute or relative to `cwd` (default: `root`); without it, `path` must
    already be relative to the project root. With `board` and `root` the
    worktree rule is enforced as well.
    """
    if isinstance(tasks, dict):
        tasks = [tasks]
    tasks = [t for t in (tasks or []) if isinstance(t, dict)]
    rel = relative(root, resolve(cwd or root, path)) if root is not None else normalized(path)
    if role == "reviewer":
        if inside(rel, REVIEWS) and not rel.startswith("../"):
            if inside(rel, APPROVALS):
                return Decision(False, "approvals", "is the approval ledger", rel)
            return Decision(True, path=rel)
        return Decision(False, "reviewer", "is outside reviews/", rel)
    if role != "worker":
        return Decision(True, path=rel)
    if board is None and root is not None:
        board = load_board(root, strict=False)
    if any(inside(rel, r) for r in RECORD_WRITES):
        return Decision(False, "lead-owned", "is lead-owned (a Polier record the tools write)", rel)
    locked = locked_by(rel, board, [t.get("id") for t in tasks])
    if locked:
        held = ", ".join(f"{i} (status {st})" for i, st in locked)
        return Decision(False, "locked", f"is in the write scope of {held}, which is locked while it is under review", rel)
    if not tasks:
        return Decision(True, path=rel)
    return decide(rel, tasks, board=board, root=root, cwd=cwd)


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


def _foreign_changes(found: List[Tuple[str, str]], task: dict, root=None) -> List[dict]:
    """Changed paths that belong to another live claim's scope.

    A path that is outside the current task's scope but inside the
    `scope_write` of a task claimed by another live session is foreign: another
    harness made it, so the current session is not blamed for it.
    """
    if root is None or not found:
        return []
    try:
        board = load_board(root, strict=False)
    except PolierError:  # pragma: no cover - load_board(strict=False) does not raise
        return []
    if not board:
        return []
    try:
        claims = live_claims(root)
    except PolierError:
        return []
    if not claims:
        return []
    by_id = {t.get("id"): t for t in tasks_of(board)}
    foreign: List[dict] = []
    for path, _reason in found:
        for claim in claims:
            claimed = claim.get("task")
            if claimed is None or claimed == task.get("id"):
                continue
            other = by_id.get(claimed)
            if other is None:
                continue
            allowed = [p for p in other.get("scope_write") or [] if isinstance(p, str)]
            if any(inside(path, entry) for entry in allowed):
                foreign.append({"path": path, "task": claimed, "harness": claim.get("harness")})
                break
    return foreign


def _fingerprint(root, rel: str) -> str:
    path = Path(root) / rel
    if not path.is_file():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _baseline_file(root, task_id: str) -> Path:
    return Path(git_common_dir(root)) / "polier" / "baselines" / f"{task_id}.json"


def snapshot(root, task_id: str) -> dict:
    """Record the changed files before a task starts; the stop check ignores them while unchanged."""
    root = Path(root)
    changes = {rel: _fingerprint(root, rel) for rel in changed_files(root)}
    target = _baseline_file(root, task_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps({"task": task_id, "root": str(root), "changes": changes}), encoding="utf-8")
    tmp.replace(target)
    return {"task": task_id, "baseline": sorted(changes)}


def _baseline(root, task_id: Optional[str]) -> dict:
    if not root or not task_id:
        return {}
    try:
        data = json.loads(_baseline_file(root, task_id).read_text(encoding="utf-8"))
    except (OSError, ValueError, PolierError):
        return {}
    if data.get("root") != str(Path(root)):
        return {}
    changes = data.get("changes")
    return changes if isinstance(changes, dict) else {}


def check_stop(changed: List[str], task: dict, allow_board: bool = False, root=None) -> dict:
    """Compare changed files (project-relative) with one task's scope.

    With `root`: files that were already changed when the task was bound
    (``snapshot``) and are unchanged since are listed under `baseline` and skipped, records the tools write
    are listed under `records` but never count, and changed files that belong
    to another live claim's scope are reported under `foreign`. `ok` is driven
    by the violations only.
    """
    before = _baseline(root, task.get("id"))
    records: List[str] = []
    unchanged: List[str] = []
    mine: List[str] = []
    for path in changed:
        if root is not None and path in before and before[path] == _fingerprint(root, path):
            unchanged.append(path)
            continue
        if any(inside(path, r) for r in RECORDS):
            records.append(path)
            continue
        mine.append(path)
    locked: List[dict] = []
    board = load_board(root, strict=False) if root is not None else None
    for path in mine:
        for tid, status in locked_by(path, board, [task.get("id")]):
            locked.append({"path": path, "task": tid, "status": status})
    locked_paths = {item["path"] for item in locked}
    found = violations([p for p in mine if p not in locked_paths], task, allow_board)
    foreign = _foreign_changes(found, task, root)
    if foreign:
        foreign_paths = {item["path"] for item in foreign}
        found = [(path, reason) for path, reason in found if path not in foreign_paths]
    held: dict = {}
    for item in locked:
        held.setdefault(item["path"], []).append(f"{item['task']} ({item['status']})")
    found = [(p, f"locked: in the scope of {', '.join(ids)}, which is under review")
             for p, ids in held.items()] + found
    return {
        "task": task.get("id"),
        "ok": not found,
        "changed": list(changed),
        "violations": [{"path": p, "reason": r} for p, r in found],
        "foreign": foreign,
        "locked": locked,
        "records": records,
        "baseline": unchanged,
        "scope_write": task.get("scope_write", []),
    }


def scope_check(root, task_id: Optional[str] = None, allow_board: bool = False) -> dict:
    """Board, task and git status of `root` in one call; raises PolierError on environment problems."""
    root = Path(root)
    board = load_board(root)
    task = pick_task(board, task_id)
    return check_stop(changed_files(root), task, allow_board, root=root)
