"""The guard decision for one tool call of a harness session.

The harness plugin asks this module (through tools/guard.py) before a write
or a shell command runs. It is the only implementation of the write and
command rules; the plugin only forwards the call and shows the answer.

A request names the project root, the session's working folder, its mode
(worker, reviewer, lead, off), the ids of the tasks bound to it, an optional
specialist role with its own write list, and either a path or a command.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from . import approvals, policy as pol
from .board import load_board, tasks_of
from .paths import inside, relative, resolve
from .scope import check_write
from .shell import process_kills

EVIDENCE = "reviews/evidence"


def _tasks(root, ids: List[str]) -> Tuple[List[dict], dict]:
    board = load_board(root, strict=False) or {}
    wanted = [str(i) for i in ids or []]
    by_id = {t.get("id"): t for t in tasks_of(board)}
    return [by_id[i] for i in wanted if i in by_id], board


def _bound(tasks: List[dict]) -> Optional[str]:
    return tasks[0].get("id") if len(tasks) == 1 else None


def _approval_hint(action: str, task: Optional[str], who: str) -> str:
    on = f" and task {task}" if task else ""
    return (f"If it is needed, call pl_approval with action {action}{on}: the {who} answers "
            "the prompt, then retry. Do not write it another way.")


def _any_grant(root, tasks: List[dict], action: str) -> bool:
    ids = [t.get("id") for t in tasks if t.get("id")]
    if not ids:
        return approvals.has_grant(root, action)
    return any(approvals.has_grant(root, action, i) for i in ids)


def _policy_path_denial(root, role: str, tasks: List[dict], rel: str, shown: str) -> Optional[str]:
    policy = pol.load_policy(root)
    if not pol.enabled(policy) or role in ("lead", "off"):
        return None
    pattern = pol.protected_match(policy, rel)
    if pattern:
        return (f"Polier: write to {shown} blocked, {pattern} is a protected path in policy.json. "
                "Only a lead session may write it: stop and report the change under open_questions "
                "instead of writing it another way.")
    deps = policy.get("dependencies") if isinstance(policy.get("dependencies"), dict) else {}
    if deps.get("approval", True) is False:
        return None
    manifest = pol.manifest_match(policy, rel)
    if manifest and not _any_grant(root, tasks, "new_dependency"):
        return (f"Polier: write to {shown} blocked, {manifest} is a dependency manifest and "
                "policy.json requires a granted new_dependency approval. "
                + _approval_hint("new_dependency", _bound(tasks), pol.approver(policy)))
    return None


def _role_denial(role: str, specialist: Optional[dict], tasks: List[dict], rel: str,
                 shown: str) -> Optional[str]:
    specialist = specialist if isinstance(specialist, dict) else {}
    writes = [w for w in specialist.get("writes") or [] if isinstance(w, str)]
    if not writes or role != "worker" or not tasks:
        return None
    if inside(rel, EVIDENCE) or any(inside(rel, entry) for entry in writes):
        return None
    title = specialist.get("title") or specialist.get("id") or "specialist"
    return (f"Polier: write to {shown} blocked, the role {title} writes only {', '.join(writes)}. "
            "If the change is needed, report it under open_questions for the right role.")


def write_denial(root, cwd, role: str, task_ids: List[str], path: str,
                 specialist: Optional[dict] = None) -> Optional[str]:
    """The reason a session may not write `path`, or None to allow it."""
    if role == "off":
        return None
    tasks, board = _tasks(root, task_ids)
    rel = relative(root, resolve(cwd or root, path))
    shown = rel or path
    verdict = check_write(path, tasks, role, root=root, cwd=cwd or root, board=board)
    if verdict.ok:
        return (_role_denial(role, specialist, tasks, rel, shown)
                or _policy_path_denial(root, role, tasks, rel, shown))
    if role == "reviewer":
        return (f"Polier: write to {shown} blocked, a reviewer session writes only under reviews/. "
                "Report the problem in the review instead of fixing it.")
    ids = ", ".join(t.get("id", "?") for t in tasks)
    if verdict.code == "worktree":
        return (f"Polier: write to {shown} blocked, {verdict.reason} ({ids}). Do the work in the "
                "task's worktree, not in the main checkout. If the change is needed elsewhere, "
                "stop and report it under open_questions.")
    allowed: List[str] = []
    for task in tasks:
        for entry in task.get("scope_write") or []:
            if isinstance(entry, str) and entry not in allowed:
                allowed.append(entry)
    return (f"Polier: write to {shown} blocked, the path {verdict.reason} of {ids}. "
            f"Allowed: {', '.join(allowed) or 'nothing'}. Do not try another way to write it. "
            "If the change is needed, stop and report it under open_questions.")


def command_denial(root, role: str, task_ids: List[str], command: str) -> Optional[str]:
    """The reason a session may not run `command`, or None to allow it."""
    if role == "off" or not (command or "").strip():
        return None
    policy = pol.load_policy(root)
    denial = pol.command_denial(policy, command, role)
    if not denial:
        return None
    if denial["rule"] == "deny":
        tasks, _ = _tasks(root, task_ids)
        task = _bound(tasks)
        on = f", task {task}" if task else ""
        return (f"Polier: command blocked, {denial['reason']}, a lead included. Do not run it "
                "another way. If the action is part of the task, "
                f"stop and ask for it with pl_approval (action release{on}) and report it under "
                "open_questions.")
    return (f"Polier: command blocked, {denial['reason']}. A worker or reviewer reports the needed "
            "change instead of running it; the lead runs it (pl_mode lead, approved by the owner).")


def decide(request: dict) -> dict:
    """One guard answer: ``{"deny": reason or None, "kills": bool}``."""
    root = request.get("root")
    if not root:
        return {"deny": None, "kills": False}
    role = request.get("role") or "worker"
    ids = request.get("tasks") or []
    if isinstance(request.get("path"), str) and request["path"]:
        reason = write_denial(root, request.get("cwd"), role, ids, request["path"],
                              request.get("specialist"))
        return {"deny": reason, "kills": False}
    command = request.get("command") or ""
    return {"deny": command_denial(root, role, ids, command),
            "kills": bool(command and process_kills(command))}
