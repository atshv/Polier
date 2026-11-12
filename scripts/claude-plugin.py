#!/usr/bin/env python3
"""Write the Claude Code plugin files that derive from the package (npm run docs).

Usage:
    python3 scripts/claude-plugin.py            write the files
    python3 scripts/claude-plugin.py --check    exit 1 when a file is stale (scripts/check.py)

Generated:
    .claude-plugin/plugin.json       manifest: version from VERSION, one agent per role
    .claude-plugin/marketplace.json  the one-plugin marketplace of this repository
    claude/agents/<role>.md          a Claude Code subagent per role in roles/roles.json

The role files stay the one source: a subagent is the role's focus, files, gates
and instructions plus the two calls that bind it (pl_role, pl_task).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import roles  # noqa: E402

MODELS = {"fast": "haiku", "standard": "sonnet", "strong": "opus"}
DESCRIPTION = ("AI software factory: runs a project through nine stations from idea to operation "
               "(web, iOS, Android, desktop, CLI, services), shows the live state in every prompt, "
               "turns every owner decision into a dialog and keeps builder agents to the plan with a "
               "write guard, recorded test evidence and reviews.")

OPTIONS = {
    "enforce": {"type": "string", "title": "Write guard",
                "description": "deny blocks writes outside the task scope, ask turns a denial into a permission prompt, off disables the guard.",
                "options": ["deny", "ask", "off"], "default": "deny"},
    "stop_check": {"type": "boolean", "title": "Stop check",
                   "description": "Compare the git diff with the worker's scope before its turn ends.", "default": True},
    "max_stop_reminders": {"type": "number", "title": "Stop reminders",
                           "description": "Reminders per turn before the stop check lets the turn end.",
                           "default": 2, "min": 0, "max": 10},
    "python": {"type": "string", "title": "Python",
               "description": "Python 3.9+ interpreter for the Polier tools. Empty: python3 (python on Windows)."},
    "owner": {"type": "string", "title": "Owner name",
              "description": "Name written into records the owner decides in a Polier dialog.", "default": "owner"},
    "context": {"type": "boolean", "title": "Live context",
                "description": "Show the live <polier> block and the guide to the model inside a Polier project.", "default": True},
}


def agent(role: Dict) -> str:
    rid = role["id"]
    reviewer = role.get("mode") == "reviewer"
    bind = ("`pl_task` with the task ID from your assignment; as a reviewer you bind it without taking the builder's claim"
            if reviewer else "`pl_task` with the task ID from your assignment; it claims the task and sets your write scope")
    reads = ", ".join(f"`{r}`" for r in role.get("reads") or []) or "the brief"
    gates = ", ".join(f"`{g}`" for g in role.get("gates") or [])
    lines = [
        "---",
        f"name: {rid}",
        f"description: Polier {role['title'].lower()}. {role['focus']} Use for a Polier task whose role is {rid}; pass the task ID.",
        f"model: {MODELS.get(role.get('model'), 'inherit')}",
        "---",
        "",
        f"You are the Polier {role['title'].lower()}{' (' + role['name'] + ')' if role.get('name') else ''}. {role['focus']}",
        "",
        "Start every assignment with these calls, in this order (the Polier tools are named `mcp__plugin_polier_polier__pl_*`; load them with ToolSearch when they are deferred):",
        "",
        f"1. `pl_role` with role `{rid}`. If it returns other instructions, the project adjusted the role: follow those.",
        f"2. {bind}.",
        "",
        f"Then read `tasks/<ID>.md` and the files your role names: {reads}.",
    ]
    if reviewer:
        lines.append("Get the review packet with `pl_review`, write only `reviews/<ID>.md` (append a round) and change no code.")
    elif gates:
        lines.append(f"Prove the work with `pl_gate`, one call per gate the task lists (typically {gates}); the record path is your evidence. Run `pl_scope_check` before you report.")
    lines += [
        "Finish with a structured result: what changed, the gate records, open_questions. Your report is a claim; the lead decides with `pl_state`.",
        "",
        "## Role instructions",
        "",
        roles.instructions(rid),
        "",
    ]
    return "\n".join(lines)


def manifest(version: str, agent_ids) -> Dict:
    env = {f"POLIER_{key.upper()}": f"${{user_config.{key}}}" for key in OPTIONS}
    return {
        "name": "polier",
        "displayName": "Polier",
        "version": version,
        "description": DESCRIPTION,
        "author": {"name": "atshv", "url": "https://github.com/atshv"},
        "homepage": "https://github.com/atshv/Polier",
        "repository": "https://github.com/atshv/Polier",
        "license": "MIT",
        "icon": "./.claude-plugin/icon.png",
        "keywords": ["polier", "software-factory", "agents", "planning", "checklist", "write-guard"],
        "skills": ["."],
        "agents": [f"./claude/agents/{rid}.md" for rid in agent_ids],
        "hooks": "./claude/hooks.json",
        "mcpServers": {
            "polier": {"command": "node", "args": ["${CLAUDE_PLUGIN_ROOT}/claude/server.mjs"], "env": env},
        },
        "userConfig": OPTIONS,
    }


def marketplace() -> Dict:
    return {
        "name": "polier",
        "owner": {"name": "atshv", "url": "https://github.com/atshv"},
        "description": "Polier, the AI software factory, for Claude Code.",
        "plugins": [{"name": "polier", "source": "./", "description": DESCRIPTION, "category": "development"}],
    }


def files() -> Dict[Path, str]:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    package = roles.load()
    out = {ROOT / "claude" / "agents" / f"{rid}.md": agent(role) for rid, role in package.items()}
    dump = lambda value: json.dumps(value, indent=2, ensure_ascii=False) + "\n"  # noqa: E731
    out[ROOT / ".claude-plugin" / "plugin.json"] = dump(manifest(version, list(package)))
    out[ROOT / ".claude-plugin" / "marketplace.json"] = dump(marketplace())
    return out


def main(argv=None) -> int:
    check = "--check" in (argv if argv is not None else sys.argv[1:])
    wanted = files()
    stale = [p for p, text in wanted.items() if not p.is_file() or p.read_text(encoding="utf-8") != text]
    agents = ROOT / "claude" / "agents"
    extra = [p for p in agents.glob("*.md") if p not in wanted] if agents.is_dir() else []
    if check:
        for path in stale + extra:
            print(f"stale: {path.relative_to(ROOT)}")
        return 1 if stale or extra else 0
    for path in extra:
        path.unlink()
    for path, text in wanted.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(f"written: {len(wanted)} Claude Code plugin files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
