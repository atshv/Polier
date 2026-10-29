"""Skills (2.6): reusable instructions for agents, stored in the project.

A skill is a Markdown file in the Agent Skills layout that Claude Code reads
natively: ``.claude/skills/<id>/SKILL.md`` with a small front matter::

    ---
    name: Write tests first
    description: Write a failing test before the code that makes it pass.
    ---
    Body in Markdown …

Interactive Claude Code sessions in the project discover these files on their
own. Headless Polier sessions get the skills of their agent profile inlined in
the prompt, so they work with any provider. Example skills ship in
``templates/skills/`` and can be copied into a project.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from .errors import PolierError
from .runtime import write_text

DIR = Path(".claude") / "skills"
TEMPLATES = Path("templates") / "skills"
ID = re.compile(r"^[a-z][a-z0-9-]{0,40}$")
MAX_TEXT = 20_000
FRONT = re.compile(r"\A---\n(.*?)\n---\n?", re.S)


def folder(root) -> Path:
    return Path(root) / DIR


def _path(root, skill_id: str) -> Path:
    if not ID.match(skill_id or ""):
        raise PolierError("skill id must be lowercase (a-z, 0-9, '-'), at most 41 characters")
    return folder(root) / skill_id / "SKILL.md"


def parse(text: str, skill_id: str) -> Dict[str, Any]:
    """Front matter (name, description) and the body of one SKILL.md."""
    meta: Dict[str, str] = {}
    body = text
    match = FRONT.match(text)
    if match:
        body = text[match.end():]
        for line in match.group(1).splitlines():
            key, sep, value = line.partition(":")
            if sep and key.strip() in ("name", "description"):
                meta[key.strip()] = value.strip().strip('"').strip("'")
    return {
        "id": skill_id,
        "name": meta.get("name") or skill_id,
        "description": meta.get("description") or "",
        "body": body.strip() + "\n" if body.strip() else "",
    }


def render(name: str, description: str, body: str) -> str:
    def clean(value: str) -> str:
        return " ".join(str(value or "").split())
    return f"---\nname: {clean(name)}\ndescription: {clean(description)}\n---\n\n{str(body or '').strip()}\n"


def _load_folder(base: Path, source: str) -> List[Dict[str, Any]]:
    skills: List[Dict[str, Any]] = []
    if not base.is_dir():
        return skills
    for entry in sorted(base.iterdir()):
        path = entry / "SKILL.md"
        if not entry.is_dir() or not ID.match(entry.name) or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        skill = parse(text, entry.name)
        skill["path"] = str(path.relative_to(base.parents[1])) if source == "project" else str(path)
        skill["source"] = source
        skills.append(skill)
    return skills


def load_all(root) -> List[Dict[str, Any]]:
    return _load_folder(folder(root), "project")


def get(root, skill_id: str) -> Dict[str, Any]:
    path = _path(root, skill_id)
    if not path.is_file():
        raise KeyError(skill_id)
    skill = parse(path.read_text(encoding="utf-8"), skill_id)
    skill["path"] = str(path.relative_to(Path(root)))
    skill["source"] = "project"
    return skill


def save(root, skill_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise PolierError("a skill must be an object")
    name = str(payload.get("name") or "").strip()
    description = str(payload.get("description") or "").strip()
    body = str(payload.get("body") or "")
    if not 1 <= len(name) <= 80:
        raise PolierError("name must be 1–80 characters")
    if not 1 <= len(description) <= 300:
        raise PolierError("description must be 1–300 characters: it tells the agent when to use the skill")
    if not body.strip():
        raise PolierError("the skill needs instructions")
    if len(body) > MAX_TEXT:
        raise PolierError(f"instructions are limited to {MAX_TEXT} characters")
    path = _path(root, skill_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text(path, render(name, description, body))
    return get(root, skill_id)


def delete(root, skill_id: str) -> Dict[str, Any]:
    path = _path(root, skill_id)
    if not path.is_file():
        raise KeyError(skill_id)
    path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass
    return {"deleted": skill_id}


def examples(package_root) -> List[Dict[str, Any]]:
    """The example skills shipped with Polier."""
    return _load_folder(Path(package_root) / TEMPLATES, "example")


def install_examples(root, package_root, ids: Optional[List[str]] = None) -> List[str]:
    """Copy shipped example skills into the project; existing skills are kept."""
    installed: List[str] = []
    for skill in examples(package_root):
        if ids and skill["id"] not in ids:
            continue
        target = _path(root, skill["id"])
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(skill["path"]), target)
        installed.append(skill["id"])
    return installed


def prompt_section(skills: List[Dict[str, Any]]) -> str:
    """The skills of an agent, inlined for a headless session prompt."""
    if not skills:
        return ""
    parts = ["## Skills", "",
             "Follow these skills whenever their description applies to what you are doing."]
    for skill in skills:
        parts += ["", f"### {skill['name']}", "", f"_When: {skill['description']}_", "", skill["body"].strip()]
    return "\n".join(parts).strip() + "\n"
