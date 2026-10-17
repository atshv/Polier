#!/usr/bin/env python3
"""Generiert STATUS.md aus board.json.

Nutzung:
    python3 tools/render_status.py examples/minimal-cli
    python3 tools/render_status.py examples/minimal-cli --out STATUS.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ICONS = {
    "done": "[x]",
    "in_progress": "[ ]",
    "claimed": "[ ]",
    "verifying": "[ ]",
    "review": "[ ]",
    "rework": "[ ]",
    "pending": "[ ]",
    "blocked": "[!]",
    "failed": "[!]",
}


def render(board: dict) -> str:
    tasks = board.get("tasks", [])
    task_stages = [t.get("stage", 1) for t in tasks if isinstance(t.get("stage"), int)]
    stage = board.get("stage", 1)
    if not isinstance(stage, int):
        stage = 1
    max_stage = max(task_stages + [stage]) if task_stages else stage

    lines = [
        "# Status",
        "",
        f"**Projekt:** {board.get('project', '?')} · **Profil:** {board.get('profile', '?')} · "
        f"**Etappe:** {stage} von {max_stage}",
        "",
        "> Automatisch aus `board.json` erzeugt. Nicht von Hand bearbeiten.",
        "",
    ]

    groups = [
        ("Erledigt", {"done"}),
        ("In Arbeit", {"claimed", "in_progress", "verifying", "review", "rework"}),
        ("Blockiert / Fehlgeschlagen", {"blocked", "failed"}),
        ("Offen", {"pending"}),
    ]
    for title, statuses in groups:
        lines.append(f"## {title}")
        lines.append("")
        selected = [t for t in tasks if t.get("status") in statuses]
        if not selected:
            lines.append("- keine")
        for task in selected:
            owner = task.get("owner") or "—"
            lines.append(
                f"- {ICONS.get(task.get('status'), '[ ]')} `{task.get('id')}` {task.get('title', '')} "
                f"— Status: `{task.get('status')}` — Owner: {owner}"
            )
        lines.append("")

    decisions = board.get("decisions", [])
    lines += ["## Entscheidungen", ""]
    if decisions:
        for decision in decisions:
            date = decision.get("date", "—")
            did = decision.get("id", "ADR-?")
            title = decision.get("title", "")
            file = decision.get("file")
            suffix = f" (`{file}`)" if file else ""
            lines.append(f"- {date} `{did}` {title}{suffix}")
    else:
        lines.append("- keine im Board; Details unter `docs/adr/`.")
    lines.append("")

    questions = [q for q in board.get("open_questions", []) if q.get("status", "open") == "open"]
    lines += ["## Offene Fragen", ""]
    if questions:
        for question in questions:
            qid = question.get("id", "Q?")
            text = question.get("question", "")
            blocks = ", ".join(question.get("blocks", [])) or "—"
            status = question.get("status", "open")
            lines.append(f"- `{qid}` {text} — blockiert: {blocks} — Status: `{status}`")
    else:
        lines.append("- keine im Board.")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", help="Projektordner mit board.json")
    parser.add_argument("--out", default="STATUS.md")
    args = parser.parse_args()

    root = Path(args.project).resolve()
    board = json.loads((root / "board.json").read_text(encoding="utf-8"))
    text = render(board)
    (root / args.out).write_text(text, encoding="utf-8")
    print(f"STATUS geschrieben: {root / args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
