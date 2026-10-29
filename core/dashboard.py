"""Read-only dashboard data: one JSON snapshot of plan, execution and decisions.

The dashboard never owns state. This module only reads the same files the CLI
tools read and applies the same core functions (``core.board``,
``core.dispatch``, ``core.runs``, ``core.approvals``, ``core.claims``,
``core.evidence``, ``core.state``) so a dashboard view can never disagree with
``tools/check.py`` or ``tools/dispatch.py``.

Shapes are versioned by ``DASHBOARD_SCHEMA`` and documented in
``docs/dashboard.md``. Every function is pure with respect to the project:
nothing here writes a file.
"""
from __future__ import annotations

import datetime as dt
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import approvals as approvals_mod
from . import board as board_mod
from . import claims as claims_mod
from . import dispatch as dispatch_mod
from . import evidence as evidence_mod
from . import paths
from . import policy as policy_mod
from . import runs as runs_mod
from . import state as state_mod
from .errors import PolierError

DASHBOARD_SCHEMA = 1

VERDICT = re.compile(r"^\s*verdict:\s*(pass|fail)\b", re.IGNORECASE | re.MULTILINE)

# Task fields the dashboard shows. Everything else stays in board.json.
TASK_FIELDS = (
    "id", "title", "goal", "why", "satisfies", "status", "depends_on",
    "complexity", "stage", "parallel_group", "scope_write", "scope_read",
    "acceptance", "gates", "owner", "branch", "worktree", "round",
    "evidence", "handoff", "scope_write_forbidden", "package", "exclusive",
    "resources", "contract_followups",
)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _read_text(path: Path, limit: int = 400_000) -> Optional[str]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return handle.read(limit)
    except OSError:
        return None


def _mtime(path: Path) -> Optional[str]:
    try:
        return dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat(timespec="seconds")
    except OSError:
        return None


def _brief(root: Path, task_id: str) -> Dict[str, Any]:
    path = root / "tasks" / f"{task_id}.md"
    present = path.is_file()
    text = _read_text(path, 4000) if present else None
    return {
        "path": f"tasks/{task_id}.md",
        "present": present,
        "words": len((text or "").split()),
        "updated": _mtime(path),
        "head": (text or "").strip().splitlines()[:1][0] if text and text.strip() else None,
    }


def _review(root: Path, task_id: str) -> Dict[str, Any]:
    path = root / "reviews" / f"{task_id}.md"
    present = path.is_file()
    text = _read_text(path, 60_000) if present else None
    verdict = None
    if text:
        match = VERDICT.search(text)
        verdict = match.group(1).lower() if match else None
    return {
        "file": f"reviews/{task_id}.md",
        "present": present,
        "verdict": verdict,
        "updated": _mtime(path),
        "head": (text or "").strip().splitlines()[0][:200] if text and text.strip() else None,
    }


def _gate_index(root: Path) -> Dict[str, List[dict]]:
    """All gate records once, grouped by task (one directory scan)."""
    grouped: Dict[str, List[dict]] = {}
    for record in evidence_mod.gate_records(root):
        task = record.get("task")
        if isinstance(task, str):
            grouped.setdefault(task, []).append(record)
    for records in grouped.values():
        records.sort(key=lambda item: str(item.get("started") or ""), reverse=True)
    return grouped


def _passing(records: List[dict]) -> set:
    passed = set()
    for record in records:
        gate = record.get("gate")
        if not isinstance(gate, str) or not gate.strip():
            continue
        if record.get("exit_code") != 0 or record.get("result") in evidence_mod.INFRA_RESULTS:
            continue
        passed.add(gate)
    return passed


def _approvals_index(root: Path) -> Dict[str, List[dict]]:
    grouped: Dict[str, List[dict]] = {}
    for record in approvals_mod.load_all(root):
        task = record.get("task")
        if isinstance(task, str):
            grouped.setdefault(task, []).append(record)
    return grouped


def _claims_index(root: Path) -> Dict[str, dict]:
    index: Dict[str, dict] = {}
    for claim in claims_mod.live_claims(root):
        task = claim.get("task")
        if isinstance(task, str):
            index[task] = claim
    return index


def _plan_index(plan: dict) -> Dict[str, Any]:
    running = {entry["id"]: entry for entry in plan.get("running", []) if isinstance(entry, dict) and entry.get("id")}
    waves: Dict[str, int] = {}
    for index, wave in enumerate(plan.get("waves", [])):
        for entry in wave.get("tasks", []) if isinstance(wave, dict) else []:
            task_id = entry.get("id") if isinstance(entry, dict) else entry
            if isinstance(task_id, str):
                waves[task_id] = index
    blocked = {entry["id"]: entry for entry in plan.get("blocked", []) if isinstance(entry, dict) and entry.get("id")}
    return {"running": running, "waves": waves, "blocked": blocked, "conflicts": plan.get("conflicts", [])}


def _budget(policy: dict, used: int) -> Dict[str, Any]:
    values = policy_mod.budget(policy) if policy else {"max_tokens_per_task": None, "warn_at": 0.8}
    maximum = values.get("max_tokens_per_task")
    warn_at = values.get("warn_at", 0.8)
    warn = bool(isinstance(maximum, int) and maximum > 0 and used >= maximum * float(warn_at))
    over = bool(isinstance(maximum, int) and maximum > 0 and used >= maximum)
    return {"used": used, "max": maximum, "warn_at": warn_at, "warn": warn, "over": over}


def _git(root: Path) -> Dict[str, Any]:
    def run(*args: str) -> Optional[str]:
        try:
            result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
        except FileNotFoundError:
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    branch = run("rev-parse", "--abbrev-ref", "HEAD")
    head = run("rev-parse", "HEAD")
    status = run("status", "--porcelain")
    log = run("log", "-8", "--pretty=format:%h|%ad|%an|%s", "--date=short")
    commits = []
    for line in (log or "").splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            commits.append({"hash": parts[0], "date": parts[1], "author": parts[2], "subject": parts[3]})
    return {
        "branch": branch,
        "head": head,
        "head_short": head[:10] if head else None,
        "dirty": bool(status.strip()) if status is not None else None,
        "changed": [line[3:] for line in (status or "").splitlines() if len(line) > 3][:50],
        "commits": commits,
    }


def _stage_titles(board: dict) -> Dict[str, str]:
    return {
        str(stage.get("id")): _text(stage.get("title")) or str(stage.get("id"))
        for stage in board.get("stages", [])
        if isinstance(stage, dict) and stage.get("id")
    }


def _task_view(root: Path, task: dict, *, policy: dict, plan_index: dict, gates: List[dict],
               approvals: List[dict], claim: Optional[dict], stage_titles: Dict[str, str],
               context: Optional[dict]) -> Dict[str, Any]:
    task_id = _text(task.get("id"))
    passed = _passing(gates)
    declared = [gate for gate in task.get("gates", []) if isinstance(gate, str)]
    run = runs_mod.summary(root, task_id) if task_id else {}
    tokens = int(run.get("tokens") or 0)
    budget = _budget(policy, tokens)
    limits = policy_mod.limits(policy) if policy else {}
    running = plan_index["running"].get(task_id)
    blocked = plan_index["blocked"].get(task_id)
    next_status = state_mod.NEXT_STATUS.get(_text(task.get("status")) or "")
    return {
        **{key: task.get(key) for key in TASK_FIELDS if key in task},
        "id": task_id,
        "stage_title": stage_titles.get(_text(task.get("stage")), _text(task.get("stage"))),
        "run": run,
        "tokens": tokens,
        "budget": budget,
        "attempt": int(run.get("attempt") or 0),
        "max_attempts": int(limits.get("max_attempts_per_task") or 0),
        "round": task.get("round", 0),
        "max_rounds": int(limits.get("max_review_rounds") or 0),
        "gates": declared,
        "gates_passed": [gate for gate in declared if gate in passed],
        "gates_missing": [gate for gate in declared if gate not in passed],
        "gate_records": len(gates),
        "last_gate": gates[0] if gates else None,
        "review": _review(root, task_id),
        "brief": _brief(root, task_id),
        "claim": claim,
        "approvals": approvals,
        "next_status": next_status,
        "ready": task_id in plan_index["waves"],
        "wave": plan_index["waves"].get(task_id),
        "running": running,
        "blocked_reason": blocked.get("reason") if blocked else None,
        "blocked_action": blocked.get("action") if blocked else None,
        "conflicted": any(
            isinstance(conflict, dict) and task_id in (conflict.get("tasks") or [])
            for conflict in plan_index["conflicts"]
        ),
        "context_pack": (context or {}).get(task_id),
    }


def _context_costs(root: Path, board: dict) -> Dict[str, int]:
    """Cheap context estimate per task: brief + the files named in scope_read."""
    costs: Dict[str, int] = {}
    for task in board.get("tasks", []):
        if not isinstance(task, dict):
            continue
        task_id = _text(task.get("id"))
        if not task_id:
            continue
        words = 0
        for rel in [f"tasks/{task_id}.md", *[entry for entry in (task.get("scope_read") or []) if isinstance(entry, str)]]:
            path = root / rel
            if path.is_file():
                try:
                    words += len(path.read_text(encoding="utf-8", errors="replace").split())
                except OSError:
                    pass
        costs[task_id] = words
    return costs


def snapshot(root, *, policy: Optional[dict] = None, plan: Optional[dict] = None,
             with_context: bool = False) -> Dict[str, Any]:
    """The whole project as the dashboard needs it: board, views, dispatch, git."""
    root = Path(root).resolve()
    board = board_mod.load_board(root)
    if board is None:
        raise PolierError(f"no board.json at {root}; run the generator first")
    policy = policy if policy is not None else policy_mod.load_policy(root)
    plan = plan if plan is not None else dispatch_mod.plan(root, board, policy)
    stage_titles = _stage_titles(board)
    gates = _gate_index(root)
    approvals = _approvals_index(root)
    claim_index = _claims_index(root)
    plan_index = _plan_index(plan)
    context = _context_costs(root, board) if with_context else {}
    tasks = [
        _task_view(root, task, policy=policy, plan_index=plan_index, gates=gates.get(_text(task.get("id")), []),
                   approvals=approvals.get(_text(task.get("id")), []),
                   claim=claim_index.get(_text(task.get("id"))), stage_titles=stage_titles,
                   context=context)
        for task in board.get("tasks", []) if isinstance(task, dict)
    ]
    counts: Dict[str, int] = {}
    for view in tasks:
        counts[str(view.get("status") or "?")] = counts.get(str(view.get("status") or "?"), 0) + 1
    tokens = sum(int(view.get("tokens") or 0) for view in tasks)
    stages = board_mod.stage_report(board, root)
    pending_approvals = [record for record in approvals_mod.load_all(root) if record.get("status") == "pending"]
    return {
        "schema": DASHBOARD_SCHEMA,
        "generated_at": _timestamp(),
        "project": {
            "name": _text(board.get("project")),
            "profile": _text(board.get("profile")),
            "stage": board.get("stage"),
            "schema_version": board.get("schema_version") or "0.9",
            "generator_version": board.get("generator_version"),
            "base_branch": board.get("base_branch"),
            "root": str(root),
            "worktrees": board.get("worktrees"),
            "packages": board.get("packages") or [],
            "resources": board.get("resources") or {},
            "contracts": board.get("contracts") or [],
            "budgets": board.get("budgets") or {},
        },
        "policy": {
            "enabled": policy_mod.enabled(policy),
            "limits": policy_mod.limits(policy),
            "budget": policy_mod.budget(policy),
            "checks": policy_mod.checks(policy),
            "approvals": (policy or {}).get("approvals", {}),
        },
        "tasks": tasks,
        "stages": stages,
        "dispatch": {
            "limits": plan.get("limits"),
            "running": plan.get("running"),
            "waves": plan.get("waves"),
            "blocked": plan.get("blocked"),
            "conflicts": plan.get("conflicts"),
            "approvals_pending": plan.get("approvals_pending"),
            "next": plan.get("next"),
        },
        "claims": sorted(claim_index.values(), key=lambda claim: str(claim.get("started") or "")),
        "approvals": {"pending": pending_approvals, "all": approvals_mod.load_all(root)},
        "usage": {
            "tokens_total": tokens,
            "budget_total": (policy_mod.budget(policy).get("max_tokens_per_task") or 0) * len(tasks)
            if policy_mod.budget(policy).get("max_tokens_per_task") else None,
        },
        "counts": counts,
        "git": _git(root),
        "paths": {
            "board": "board.json",
            "runs": "runs/",
            "reviews": "reviews/",
            "tasks": "tasks/",
            "policy": "policy.json",
        },
    }


def task_detail(root, task_id: str) -> Dict[str, Any]:
    """One task with everything the detail drawer shows (texts, records, events)."""
    root = Path(root).resolve()
    board = board_mod.load_board(root)
    if board is None:
        raise PolierError(f"no board.json at {root}")
    task = next((entry for entry in board.get("tasks", []) if isinstance(entry, dict)
                 and _text(entry.get("id")) == task_id), None)
    if task is None:
        raise KeyError(task_id)
    policy = policy_mod.load_policy(root)
    plan = dispatch_mod.plan(root, board, policy)
    records = evidence_mod.gate_records(root, task_id)
    view = _task_view(root, task, policy=policy, plan_index=_plan_index(plan), gates=records,
                      approvals=_approvals_index(root).get(task_id, []),
                      claim=_claims_index(root).get(task_id), stage_titles=_stage_titles(board),
                      context=None)
    brief_text = _read_text(root / "tasks" / f"{task_id}.md")
    review_text = _read_text(root / "reviews" / f"{task_id}.md")
    run = runs_mod.load_run(root, task_id)
    events = [
        {"at": event.get("at"), "kind": event.get("kind"), "data": event.get("data")}
        for event in run.get("events", []) if isinstance(event, dict)
    ]
    logs = []
    for record in records:
        log_name = record.get("log")
        if isinstance(log_name, str):
            log_path = root / "reviews" / "evidence" / log_name
            logs.append({
                "gate": record.get("gate"),
                "record": _rel(root, root / "reviews" / "evidence" / (str(record.get("log", "")).replace(".log", ".json"))),
                "log": f"reviews/evidence/{log_name}",
                "present": log_path.is_file(),
                "size": log_path.stat().st_size if log_path.is_file() else 0,
            })
    stage = next((entry for entry in board.get("stages", []) if isinstance(entry, dict)
                  and entry.get("id") == task.get("stage")), None)
    return {
        "schema": DASHBOARD_SCHEMA,
        "task": view,
        "brief": {"text": brief_text, "path": f"tasks/{task_id}.md"},
        "review": {"text": review_text, "path": f"reviews/{task_id}.md"},
        "run": run,
        "events": events,
        "gate_records": records,
        "gate_logs": logs,
        "approvals": approvals_mod.load_all(root),
        "claim": _claims_index(root).get(task_id),
        "stage": stage,
        "git": _git(root),
    }


def activity(root, limit: int = 120) -> List[Dict[str, Any]]:
    """Merge run events, approvals and usage records into one newest-first feed."""
    root = Path(root).resolve()
    items: List[Dict[str, Any]] = []
    runs_dir = root / "runs"
    if runs_dir.is_dir():
        for path in sorted(runs_dir.glob("*.json")):
            try:
                record = runs_mod.load_run(root, path.stem)
            except (PolierError, ValueError, OSError):
                continue
            for event in record.get("events", []):
                if not isinstance(event, dict):
                    continue
                data = event.get("data") or {}
                items.append({
                    "at": event.get("at"),
                    "kind": event.get("kind"),
                    "task": record.get("task"),
                    "summary": _activity_summary(event.get("kind"), data),
                    "data": data,
                })
    for record in approvals_mod.load_all(root):
        when = record.get("approved_at") or record.get("requested_at")
        items.append({
            "at": when,
            "kind": "approval",
            "task": record.get("task"),
            "summary": f"{record.get('id')} {record.get('action')} {record.get('status')}",
            "data": record,
        })
    items = [item for item in items if item.get("at")]
    items.sort(key=lambda item: str(item.get("at")), reverse=True)
    return items[: max(1, int(limit))]


def _activity_summary(kind: Any, data: dict) -> str:
    if kind == "gate":
        return f"gate {data.get('gate')}: {data.get('result')}"
    if kind == "state":
        return f"{data.get('from')} -> {data.get('to')}" + (f" ({data.get('note')})" if data.get("note") else "")
    if kind == "review":
        return f"review {data.get('verdict') or data.get('result') or ''}".strip()
    if kind == "start":
        return "attempt started"
    if kind == "note":
        return str(data.get("note") or data.get("text") or "note")
    if kind == "approval":
        return f"{data.get('id')} {data.get('action')} {data.get('status')}"
    if kind == "usage":
        return f"usage {data.get('tokens')} tokens"
    return str(kind)


def task_log(root, task_id: str, log_name: str) -> str:
    """The text of one gate log; only files under reviews/evidence/ are served."""
    root = Path(root).resolve()
    name = _text(log_name)
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise PolierError("invalid log name")
    folder = (root / "reviews" / "evidence").resolve()
    path = (folder / name).resolve()
    if folder not in path.parents or not path.is_file():
        raise PolierError("log not found")
    return _read_text(path) or ""


def repo_files(root, prefix: str = "", limit: int = 200) -> List[Dict[str, Any]]:
    """Project files under `prefix` (relative), for the file picker in the UI."""
    root = Path(root).resolve()
    base = (root / prefix).resolve() if prefix else root
    if base != root and root not in base.parents:
        raise PolierError("path outside the project")
    if not base.is_dir():
        return []
    entries: List[Dict[str, Any]] = []
    for path in sorted(base.iterdir()):
        if path.name.startswith((".git", "node_modules", "__pycache__", ".turbo", "dist", "build")):
            continue
        rel = path.relative_to(root).as_posix()
        entries.append({"path": rel, "name": path.name, "dir": path.is_dir()})
        if len(entries) >= limit:
            break
    return entries


def file_preview(root, rel: str, limit: int = 200_000) -> Dict[str, Any]:
    """Read one project file (bounded); paths outside the project are refused."""
    root = Path(root).resolve()
    candidate = (root / rel).resolve()
    if candidate != root and root not in candidate.parents:
        raise PolierError("path outside the project")
    if not candidate.is_file():
        raise PolierError("file not found")
    return {"path": paths.relative(root, candidate), "text": _read_text(candidate, limit) or ""}
