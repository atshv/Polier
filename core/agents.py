"""Agent profiles (2.5): named, reusable setups for headless sessions.

An agent is what you assign to a task: a role (worker, reviewer or lead), an
optional model, standing instructions, the skills it follows and the MCP
connectors it may use. Profiles are committed in ``agents.json`` so the team
shares them; the connectors they name are configured per machine (see
``core.mcp_connectors``), because they may carry local commands and secrets.

Without ``agents.json`` three built-in profiles are offered — Builder,
Reviewer and Lead — that match the plain session roles.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .errors import PolierError
from .runtime import write_json

FILE = "agents.json"
VERSION = 1
ID = re.compile(r"^[a-z][a-z0-9-]{0,40}$")
ROLES = ("worker", "reviewer", "lead")
FIELDS = frozenset({"id", "name", "role", "description", "model", "instructions",
                    "skills", "connectors", "worktree"})

BUILTIN: List[Dict[str, Any]] = [
    {"id": "builder", "name": "Builder", "role": "worker",
     "description": "Implements a task inside its scope and proves it with the gates.",
     "model": None, "instructions": "", "skills": ["stay-in-scope", "test-first", "prove-with-gates", "write-a-handoff"],
     "connectors": [], "worktree": True},
    {"id": "reviewer", "name": "Reviewer", "role": "reviewer",
     "description": "Reviews a finished task against its brief and evidence and writes the verdict.",
     "model": None, "instructions": "", "skills": ["review-checklist"],
     "connectors": [], "worktree": False},
    {"id": "lead", "name": "Lead", "role": "lead",
     "description": "Coordinates a task: runs gates and moves the status through the state machine.",
     "model": None, "instructions": "", "skills": ["prove-with-gates"],
     "connectors": [], "worktree": False},
]


def path(root) -> Path:
    return Path(root) / FILE


def errors(agent: Dict[str, Any]) -> List[str]:
    if not isinstance(agent, dict):
        return ["agent must be an object"]
    found: List[str] = []
    for field in sorted(set(agent) - FIELDS):
        found.append(f"unknown field {field!r}")
    if not isinstance(agent.get("id"), str) or not ID.match(agent["id"]):
        found.append("id must be lowercase (a-z, 0-9, '-')")
    name = agent.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60:
        found.append("name must be 1–60 characters")
    if agent.get("role") not in ROLES:
        found.append(f"role must be one of {', '.join(ROLES)}")
    for field, limit in (("description", 300), ("instructions", 8000), ("model", 80)):
        value = agent.get(field)
        if value is not None and (not isinstance(value, str) or len(value) > limit):
            found.append(f"{field} must be text of at most {limit} characters")
    for field in ("skills", "connectors"):
        value = agent.get(field, [])
        if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
            found.append(f"{field} must be a list of ids")
    if "worktree" in agent and not isinstance(agent["worktree"], bool):
        found.append("worktree must be true or false")
    return [f"agent {agent.get('id', '?')}: {problem}" for problem in found]


def _normalise(agent: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": agent["id"], "name": agent["name"].strip(), "role": agent["role"],
        "description": (agent.get("description") or "").strip(),
        "model": (agent.get("model") or "").strip() or None,
        "instructions": (agent.get("instructions") or "").strip(),
        "skills": list(dict.fromkeys(agent.get("skills") or [])),
        "connectors": list(dict.fromkeys(agent.get("connectors") or [])),
        "worktree": bool(agent.get("worktree", False)),
    }


def load(root) -> Dict[str, Any]:
    """{"agents": [...], "builtin": bool, "errors": [...]} — built-ins without a file."""
    file = path(root)
    if not file.is_file():
        return {"version": VERSION, "agents": [dict(agent) for agent in BUILTIN], "builtin": True, "errors": []}
    try:
        value = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"version": VERSION, "agents": [dict(agent) for agent in BUILTIN], "builtin": True,
                "errors": [f"{FILE}: {exc}"]}
    agents = value.get("agents") if isinstance(value, dict) else None
    if not isinstance(agents, list):
        return {"version": VERSION, "agents": [], "builtin": False, "errors": [f"{FILE}: agents must be a list"]}
    problems: List[str] = []
    good: List[Dict[str, Any]] = []
    for agent in agents:
        found = errors(agent)
        problems += found
        if not found:
            good.append(_normalise(agent))
    return {"version": VERSION, "agents": good, "builtin": False, "errors": problems}


def get(root, agent_id: str) -> Dict[str, Any]:
    for agent in load(root)["agents"]:
        if agent["id"] == agent_id:
            return agent
    raise KeyError(agent_id)


def save(root, agents: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate and write the whole list (the dashboard edits it as one file)."""
    if not isinstance(agents, list):
        raise PolierError("agents must be a list")
    problems: List[str] = []
    seen = set()
    for agent in agents:
        problems += errors(agent)
        agent_id = agent.get("id") if isinstance(agent, dict) else None
        if agent_id in seen:
            problems.append(f"agent {agent_id}: id is used twice")
        seen.add(agent_id)
    if problems:
        raise PolierError("; ".join(problems))
    value = {"version": VERSION, "agents": [_normalise(agent) for agent in agents]}
    write_json(path(root), value)
    return load(root)


def session_options(agent: Dict[str, Any], skills: List[Dict[str, Any]],
                    note: Optional[str] = None) -> Dict[str, Any]:
    """What a session needs from a profile: role, model, worktree and the prompt add-on."""
    from .skills import prompt_section

    parts: List[str] = [f"## Agent: {agent['name']}"]
    if agent.get("description"):
        parts += ["", agent["description"]]
    if agent.get("instructions"):
        parts += ["", agent["instructions"]]
    section = prompt_section(skills)
    if section:
        parts += ["", section.strip()]
    if note:
        parts += ["", "## Operator note", note.strip()]
    return {"role": agent["role"], "model": agent.get("model"),
            "worktree": bool(agent.get("worktree")), "note": "\n".join(parts).strip()}
