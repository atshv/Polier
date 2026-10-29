"""Modules (2.2): the package map as the structural view of the project.

A module is a ``packages[]`` entry (package, service, app, tool, infra). The
view combines the board's package map with the tasks that live there, the
contracts that touch it, the documentation it must carry and the real effort
from the worklog. Tasks without a package are reported separately, so the view
never hides work.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import board as board_mod
from . import dashboard as dashboard_mod
from . import worklog as worklog_mod

DOCS = ("README.md", "ARCHITECTURE.md")
ATTENTION = ("blocked", "failed")


def _module_health(open_tasks: int, blocked: int, gates_missing: int, docs_missing: int) -> str:
    if blocked:
        return "attention"
    if gates_missing:
        return "watch"
    if docs_missing:
        return "watch"
    if open_tasks:
        return "ok"
    return "done"


def build(root, *, snapshot: Optional[dict] = None,
          worklog: Optional[dict] = None) -> Dict[str, Any]:
    root = Path(root).resolve()
    snapshot = snapshot if snapshot is not None else dashboard_mod.snapshot(root)
    worklog = worklog if worklog is not None else worklog_mod.project_worklog(root, snapshot["tasks"])
    rows = {row["id"]: row for row in worklog.get("tasks") or []}
    board = board_mod.load_board(root, strict=False)
    packages = [package for package in (board or {}).get("packages") or [] if isinstance(package, dict)]
    contracts = [contract for contract in (board or {}).get("contracts") or [] if isinstance(contract, dict)]
    tasks = snapshot.get("tasks") or []
    modules: List[Dict[str, Any]] = []
    assigned: set = set()
    for package in packages:
        path = str(package.get("path") or "")
        module_tasks = [task for task in tasks if str(task.get("package") or "") == path]
        assigned.update(str(task.get("id")) for task in module_tasks)
        counts: Dict[str, int] = {}
        for task in module_tasks:
            status = str(task.get("status") or "?")
            counts[status] = counts.get(status, 0) + 1
        open_tasks = [task for task in module_tasks if task.get("status") != "done"]
        blocked = len([task for task in module_tasks if task.get("status") in ATTENTION])
        waiting = len([task for task in module_tasks
                       if task.get("status") not in ATTENTION and task.get("blocked_reason")])
        gates_missing = sum(len(task.get("gates_missing") or []) for task in open_tasks)
        docs = [{"path": f"{path}/{name}".replace("//", "/"), "present": (root / path / name).is_file()}
                for name in DOCS]
        docs_missing = len([entry for entry in docs if not entry["present"]])
        module_contracts = []
        for contract in contracts:
            dependants = [entry for entry in contract.get("dependants") or [] if isinstance(entry, str)]
            if contract.get("path") == path or path in dependants:
                module_contracts.append({
                    "name": contract.get("name"),
                    "version": contract.get("version"),
                    "path": contract.get("path"),
                    "schema_files": len(contract.get("schema_files") or []),
                })
        totals = {
            "tasks": len(module_tasks),
            "done": counts.get("done", 0),
            "open": len(open_tasks),
            "blocked": blocked,
            "tokens": sum(int(rows.get(str(task.get("id")), {}).get("tokens") or 0) for task in module_tasks),
            "estimate_hours": round(sum(float(rows.get(str(task.get("id")), {}).get("estimate_hours") or 0.0)
                                        for task in module_tasks), 1),
            "actual_hours": round(sum(float(rows.get(str(task.get("id")), {}).get("actual_hours") or 0.0)
                                      for task in module_tasks), 1),
        }
        modules.append({
            "path": path,
            "kind": package.get("kind"),
            "may_import": package.get("may_import") or [],
            "counts": counts,
            "totals": totals,
            "progress": round(totals["done"] / totals["tasks"], 3) if totals["tasks"] else 0.0,
            "docs": docs,
            "contracts": module_contracts,
            "health": _module_health(totals["open"], blocked, gates_missing, docs_missing),
            "waiting": waiting,
            "health_reasons": [
                reason for reason, present in (
                    ("blocked tasks", blocked),
                    ("gates missing", gates_missing),
                    ("missing package docs", docs_missing),
                ) if present
            ],
            "tasks": [{"id": task.get("id"), "title": task.get("title"),
                       "status": task.get("status"), "owner": task.get("owner"),
                       "gates_missing": task.get("gates_missing") or []}
                      for task in module_tasks],
        })
    unassigned = [task for task in tasks if str(task.get("id")) not in assigned]
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "modules": modules,
        "unassigned": {
            "tasks": [{"id": task.get("id"), "title": task.get("title"),
                       "status": task.get("status"), "package": task.get("package")}
                      for task in unassigned],
            "count": len(unassigned),
        },
        "totals": {
            "modules": len(modules),
            "tasks": sum(module["totals"]["tasks"] for module in modules),
            "done": sum(module["totals"]["done"] for module in modules),
            "attention": len([module for module in modules if module["health"] == "attention"]),
            "watch": len([module for module in modules if module["health"] == "watch"]),
        },
    }
