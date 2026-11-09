"""What a reviewer needs for one task, gathered in one place.

The packet names the brief, the earlier review rounds, the latest gate record
per gate, the files the task changed and their diff, restricted to the task's
write scope. A hand-built packet tends to miss a record or the last review
round; this one is built the same way every time.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import List, Optional

from . import evidence
from .board import load_board, pick_task
from .paths import inside
from .scope import changed_files

MAX_DIFF = 60_000


def _git(root, *args) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    return result.stdout if result.returncode == 0 else ""


def _in_scope(path: str, scope: List[str]) -> bool:
    return any(inside(path, entry) for entry in scope)


def _verdicts(root, task_id: str) -> List[str]:
    path = Path(root) / "reviews" / f"{task_id}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return [v.lower() for v in evidence.REVIEW_VERDICT.findall(text)]


def _latest_records(root, task_id: str, gates: List[str]) -> List[dict]:
    latest = {}
    for path in evidence.record_files(root, task_id):
        record = json.loads(path.read_text(encoding="utf-8"))
        latest[record.get("gate")] = {
            "gate": record.get("gate"),
            "record": f"reviews/evidence/{path.name}",
            "log": f"reviews/evidence/{record.get('log')}" if record.get("log") else None,
            "passed": record.get("exit_code") == 0 and record.get("result") not in evidence.INFRA_RESULTS,
        }
    return [latest.get(g) or {"gate": g, "record": None, "passed": False} for g in gates]


def packet(root, task_id: Optional[str] = None) -> dict:
    root = Path(root)
    board = load_board(root)
    task = pick_task(board, task_id)
    tid = task["id"]
    scope = [p for p in task.get("scope_write") or [] if isinstance(p, str)]
    base = board.get("base_branch") or "main"
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    committed: List[str] = []
    if branch and branch != base and _git(root, "rev-parse", "--verify", base).strip():
        committed = [line for line in _git(root, "diff", "--name-only", f"{base}...HEAD").splitlines() if line]
    files = sorted({p for p in committed + changed_files(root) if _in_scope(p, scope)})
    diff = ""
    if committed:
        diff += _git(root, "diff", f"{base}...HEAD", "--", *scope)
    diff += _git(root, "diff", "HEAD", "--", *scope)
    untracked = [p for p in _git(root, "ls-files", "--others", "--exclude-standard", "--", *scope).splitlines() if p]
    for rel in untracked:
        try:
            body = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            body = "<binary or unreadable>"
        diff += f"--- /dev/null\n+++ b/{rel}\n" + "".join(f"+{line}\n" for line in body.splitlines())
    gates = [g for g in task.get("gates") or [] if isinstance(g, str)]
    records = _latest_records(root, tid, gates)
    return {
        "task": tid,
        "title": task.get("title"),
        "brief": f"tasks/{tid}.md" if (root / "tasks" / f"{tid}.md").is_file() else None,
        "acceptance": task.get("acceptance", []),
        "review_file": f"reviews/{tid}.md",
        "earlier_verdicts": _verdicts(root, tid),
        "gates": records,
        "gates_green": bool(records) and all(r["passed"] for r in records),
        "files": files,
        "diff": diff[:MAX_DIFF],
        "diff_truncated": len(diff) > MAX_DIFF,
    }
