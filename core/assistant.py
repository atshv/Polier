"""AI assistant (2.4): conversations, project context and answer parsing.

The assistant is a headless agent session with a small, read-only briefing: the
current plan state, the next wave, blocked tasks, approvals, recent activity and
the task list in compact form. It answers questions and may return **proposals**
(structured action suggestions); nothing is executed by the answer itself — the
dashboard shows the proposals and applies them only after explicit confirmation.

Conversations live in the dashboard runtime folder (local, never committed):
``<git-common-dir>/polier/dashboard/assistant/<id>.json``.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import dashboard as dashboard_mod
from . import intake as intake_mod
from . import runtime as runtime_mod
from . import worklog as worklog_mod

VERSION = 1
PROPOSAL_KINDS = ("state", "plan_task", "gate", "session", "note")
MAX_MESSAGES = 100
MAX_PROMPT_TASKS = 140


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def folder(root) -> Path:
    return runtime_mod.sub(root, "assistant")


def _path(root, conversation_id: str) -> Path:
    if not re.match(r"^conv-[0-9A-Za-z-]{6,60}$", conversation_id or ""):
        raise KeyError(conversation_id)
    return folder(root) / f"{conversation_id}.json"


def list_conversations(root) -> List[Dict[str, Any]]:
    base = folder(root)
    result: List[Dict[str, Any]] = []
    for path in sorted(base.glob("conv-*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(value, dict):
            continue
        result.append({
            "id": value.get("id"), "title": value.get("title"),
            "created": value.get("created"), "updated": value.get("updated"),
            "messages": len(value.get("messages") or []),
            "pending": value.get("pending"),
        })
    result.sort(key=lambda item: str(item.get("updated") or ""), reverse=True)
    return result


def load(root, conversation_id: str) -> Dict[str, Any]:
    target = _path(root, conversation_id)
    if not target.is_file():
        raise KeyError(conversation_id)
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise KeyError(conversation_id) from exc
    if not isinstance(value, dict):
        raise KeyError(conversation_id)
    value.setdefault("version", VERSION)
    value.setdefault("messages", [])
    value.setdefault("pending", None)
    return value


def save(root, conversation: Dict[str, Any]) -> Dict[str, Any]:
    conversation["version"] = VERSION
    conversation["updated"] = _now()
    messages = conversation.get("messages")
    if isinstance(messages, list) and len(messages) > MAX_MESSAGES:
        conversation["messages"] = messages[-MAX_MESSAGES:]
    runtime_mod.write_json(_path(root, str(conversation["id"])), conversation)
    return conversation


def create(root, title: Optional[str] = None) -> Dict[str, Any]:
    conversation_id = "conv-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    conversation = {
        "version": VERSION,
        "id": conversation_id,
        "title": (title or "New conversation")[:80],
        "created": _now(),
        "updated": _now(),
        "messages": [],
        "pending": None,
    }
    return save(root, conversation)


def delete(root, conversation_id: str) -> Dict[str, Any]:
    target = _path(root, conversation_id)
    if not target.is_file():
        raise KeyError(conversation_id)
    target.unlink()
    return {"id": conversation_id, "deleted": True}


def append_message(root, conversation_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
    conversation = load(root, conversation_id)
    entry = {"at": _now(), **message}
    conversation["messages"].append(entry)
    if conversation.get("title") in (None, "", "New conversation") and message.get("role") == "user":
        conversation["title"] = str(message.get("content") or "New conversation")[:80]
    return save(root, conversation)


def set_pending(root, conversation_id: str, pending: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    conversation = load(root, conversation_id)
    conversation["pending"] = pending
    return save(root, conversation)


def _task_line(task: dict) -> str:
    gates = "%d/%d" % (len(task.get("gates_passed") or []), len(task.get("gates") or []))
    parts = [str(task.get("id")), str(task.get("status")), str(task.get("stage") or "-")]
    if task.get("owner"):
        parts.append("owner=" + str(task.get("owner")))
    if task.get("package"):
        parts.append("pkg=" + str(task.get("package")))
    parts.append("gates=" + gates)
    if task.get("blocked_reason"):
        parts.append("blocked=" + str(task.get("blocked_reason")))
    if task.get("tokens"):
        parts.append("tokens=" + str(task.get("tokens")))
    parts.append("| " + str(task.get("title") or ""))
    return " ".join(parts)


def build_prompt(root, conversation: Dict[str, Any], message: str) -> str:
    """The complete assistant prompt: context, history, question, output format."""
    snapshot = dashboard_mod.snapshot(root)
    project = snapshot.get("project") or {}
    tasks = snapshot.get("tasks") or []
    lines: List[str] = [
        "You are the Polier project assistant: a read-only analyst for the owner of this project.",
        "Answer from the facts below; cite file paths or task IDs when you use them.",
        "Never change files, board state or run commands. Suggest actions as proposals only.",
        "Answer in the language of the user's question (German question → German answer).",
        "",
        f"Project: {project.get('name')} · profile {project.get('profile')} · stage {project.get('stage')} · generator {project.get('generator_version')}",
        f"Counts: {json.dumps(snapshot.get('counts') or {}, ensure_ascii=False)}",
        f"Tokens: {((snapshot.get('usage') or {}).get('tokens_total'))}",
    ]
    stages = snapshot.get("stages") or []
    if stages:
        lines.append("Stages:")
        for stage in stages:
            lines.append(f"- {stage.get('id')}: {stage.get('title')} | decision={stage.get('owner_decision')} "
                         f"complete={stage.get('complete')} open={len(stage.get('tasks_open') or [])} "
                         f"missing_gates={stage.get('missing_gates')}")
    dispatch = snapshot.get("dispatch") or {}
    if dispatch.get("next"):
        lines.append("Next wave: " + ", ".join(str(item) for item in dispatch.get("next") or []))
    if snapshot.get("approvals", {}).get("pending"):
        lines.append("Pending approvals:")
        for record in snapshot["approvals"]["pending"]:
            lines.append(f"- {record.get('id')} {record.get('action')} task={record.get('task')} note={record.get('note')}")
    claims = snapshot.get("claims") or []
    if claims:
        lines.append("Live claims: " + "; ".join(
            f"{claim.get('task')} by {claim.get('harness')}/{claim.get('session')}" for claim in claims))
    sessions = worklog_mod.session_records(root)[:8]
    if sessions:
        lines.append("Recent sessions:")
        for session in sessions:
            lines.append(f"- {session.get('id')} {session.get('role')} {session.get('status')} "
                         f"task={session.get('task')} tokens={session.get('tokens')} started={session.get('started')}")
    intake_summary = intake_mod.summary(root)
    if intake_summary.get("total"):
        proposed = [entry for entry in intake_mod.load_all(root, "proposed")][:8]
        lines.append(f"Intake: {intake_summary['counts']}")
        for entry in proposed:
            lines.append(f"- {entry.get('id')} [{entry.get('kind')}/{entry.get('priority')}] {entry.get('title')}")
    lines.append("Tasks (id status stage owner gates blocked tokens | title):")
    for task in tasks[:MAX_PROMPT_TASKS]:
        lines.append("- " + _task_line(task))
    if len(tasks) > MAX_PROMPT_TASKS:
        lines.append(f"... {len(tasks) - MAX_PROMPT_TASKS} more tasks omitted")
    history = conversation.get("messages") or []
    if history:
        lines += ["", "Conversation so far:"]
        for entry in history[-12:]:
            role = entry.get("role")
            content = str(entry.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                lines.append(f"{role.capitalize()}: {content[:2000]}")
    lines += [
        "",
        "User question:",
        message.strip(),
        "",
        "Answer format:",
        "- Write the answer as plain Markdown, concise and specific.",
        "- If an action would help, add a fenced JSON block at the end:",
        '```json',
        '{"proposals": [{"kind": "state", "title": "…", "reason": "…", "payload": {"task": "M03", "status": "blocked", "note": "…"}}]}',
        '```',
        "- Allowed kinds and payloads:",
        '  state: {"task","status","note"?}; plan_task: {"title","goal","stage","scope_write","acceptance","gates", ...};',
        '  gate: {"task","name","command"?}; session: {"task","role","note"?}; note: {"text"}.',
        "- Only propose what the facts support; no proposal is required.",
    ]
    return "\n".join(lines).strip() + "\n"


def parse_answer(text: str) -> Dict[str, Any]:
    """Split an assistant answer into prose and validated proposals."""
    raw = str(text or "").strip()
    proposals: List[Dict[str, Any]] = []
    answer = raw
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    candidates = list(reversed(blocks))
    if not candidates:
        candidates = [raw[raw.rfind("{"):]] if "{" in raw else []
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if not isinstance(value, dict):
            continue
        if isinstance(value.get("answer"), str) and value["answer"].strip():
            answer = value["answer"].strip()
        raw_proposals = value.get("proposals")
        if isinstance(raw_proposals, list):
            proposals = [_proposal(item) for item in raw_proposals if isinstance(item, dict)]
            proposals = [item for item in proposals if item]
            # Remove the JSON block from the prose answer.
            answer = re.sub(r"```(?:json)?\s*\{.*?\}\s*```", "", raw, flags=re.DOTALL).strip()
        break
    if not proposals:
        cleaned = re.sub(r"```(?:json)?\s*\{.*?\}\s*```", "", raw, flags=re.DOTALL).strip()
        answer = cleaned or raw
    return {"answer": answer or "(no answer)", "proposals": proposals}


def _proposal(value: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    kind = str(value.get("kind") or "").strip()
    if kind not in PROPOSAL_KINDS:
        return None
    payload = value.get("payload") if isinstance(value.get("payload"), dict) else {}
    return {
        "kind": kind,
        "title": str(value.get("title") or kind.replace("_", " "))[:160],
        "reason": str(value.get("reason") or "")[:600],
        "payload": payload,
    }
