"""Gate command suggestions from the project's own documentation.

Polier keeps gate *names* on the board and gate *commands* in the project's
quality document (for example ``docs/quality.md``). The dashboard uses this
parser to prefill the gate runner, so the UI suggests the same command the
project already documents instead of inventing one.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict

NAME = re.compile(r"[a-z][a-z0-9-]{1,40}")


def suggest_gate_commands(root) -> Dict[str, str]:
    """Map gate name -> command from a Markdown table in docs/quality.md."""
    path = Path(root) / "docs" / "quality.md"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    commands: Dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        name = cells[0].strip("`").strip()
        command = cells[1].strip()
        if command.startswith("`") and command.endswith("`"):
            command = command[1:-1]
        if NAME.fullmatch(name) and command and "`" not in command:
            commands[name] = command
    return commands
