"""Requirement coverage (2.2): every definition-of-done item, its tasks and evidence.

Polier tasks list ``satisfies: ["D3", …]``; the definitions live in the
project's ``docs/quality.md`` (``**D3** …``). This module joins both: for every
requirement it shows the tasks, their status, the passing evidence and a state
(``covered`` / ``partial`` / ``open`` / ``missing``). Codes that tasks reference
but the document does not define are reported instead of hidden.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import dashboard as dashboard_mod
from . import evidence as evidence_mod

DEFINITION = re.compile(r"\*\*(D[0-9]+)\*\*\s*(.*)")
STATE_ORDER = ("missing", "open", "partial", "covered")
ACTIVE = {"in_progress", "verifying", "review", "rework", "claimed"}


def definitions(root) -> List[Dict[str, str]]:
    """The ``**Dn** text`` requirements of ``docs/quality.md``, in document order."""
    path = Path(root) / "docs" / "quality.md"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    found: List[Dict[str, str]] = []
    seen = set()
    for line in text.splitlines():
        match = DEFINITION.search(line)
        if not match:
            continue
        requirement, description = match.group(1), match.group(2).strip()
        if requirement in seen:
            continue
        seen.add(requirement)
        found.append({"id": requirement, "title": description[:120],
                      "definition": description})
    return found


def build(root, *, snapshot: Optional[dict] = None,
          definitions_list: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    root = Path(root).resolve()
    snapshot = snapshot if snapshot is not None else dashboard_mod.snapshot(root)
    definitions_list = definitions_list if definitions_list is not None else definitions(root)
    tasks = snapshot.get("tasks") or []
    records = evidence_mod.gate_records(root)
    evidence_by_task: Dict[str, int] = {}
    for record in records:
        task_id = record.get("task")
        if isinstance(task_id, str) and record.get("result") == "pass" and record.get("exit_code") == 0:
            evidence_by_task[task_id] = evidence_by_task.get(task_id, 0) + 1
    by_requirement: Dict[str, List[dict]] = {}
    referenced: set = set()
    for task in tasks:
        for requirement in task.get("satisfies") or []:
            if not isinstance(requirement, str):
                continue
            referenced.add(requirement)
            by_requirement.setdefault(requirement, []).append(task)

    rows: List[Dict[str, Any]] = []
    defined = {requirement["id"]: requirement for requirement in definitions_list}
    for requirement in definitions_list:
        requirement_id = requirement["id"]
        linked = by_requirement.get(requirement_id, [])
        rows.append(_row(requirement_id, requirement, linked, evidence_by_task))
    undefined = sorted(referenced - set(defined))
    for requirement_id in undefined:
        rows.append(_row(requirement_id, None, by_requirement.get(requirement_id, []),
                         evidence_by_task))
    summary = {
        "defined": len(definitions_list),
        "referenced": len(referenced),
        "covered": len([row for row in rows if row["state"] == "covered"]),
        "partial": len([row for row in rows if row["state"] == "partial"]),
        "open": len([row for row in rows if row["state"] == "open"]),
        "missing": len([row for row in rows if row["state"] == "missing"]),
        "uncovered": len([row for row in rows if row["state"] in ("missing", "open")]),
        "undefined": undefined,
    }
    return {"requirements": rows, "summary": summary}


def _row(requirement_id: str, definition: Optional[dict], tasks: List[dict],
         evidence_by_task: Dict[str, int]) -> Dict[str, Any]:
    task_rows = [{"id": task.get("id"), "title": task.get("title"),
                  "status": task.get("status"), "owner": task.get("owner"),
                  "stage": task.get("stage"),
                  "evidence": evidence_by_task.get(str(task.get("id")), 0)}
                 for task in tasks]
    total = len(task_rows)
    done = len([task for task in task_rows if task["status"] == "done"])
    active = len([task for task in task_rows if task["status"] in ACTIVE])
    if total == 0:
        state = "missing"
    elif done == total:
        state = "covered"
    elif done or active:
        state = "partial"
    else:
        state = "open"
    return {
        "id": requirement_id,
        "title": (definition or {}).get("title") or "Undefined requirement (referenced by tasks)",
        "definition": (definition or {}).get("definition"),
        "defined": definition is not None,
        "state": state,
        "tasks": task_rows,
        "total": total,
        "done": done,
        "active": active,
        "coverage": round(done / total, 3) if total else 0.0,
        "evidence": sum(task["evidence"] for task in task_rows),
    }
