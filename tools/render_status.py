#!/usr/bin/env python3
"""Generate STATUS.md from board.json.

Usage:
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
        f"**Project:** {board.get('project', '?')} · **Profile:** {board.get('profile', '?')} · "
        f"**Stage:** {stage} of {max_stage}",
        "",
        "> Generated from `board.json`. Do not edit by hand.",
        "",
    ]

    # Ready now: pending tasks whose dependencies are all done
    done = {t.get("id") for t in tasks if t.get("status") == "done"}
    ready = [t for t in tasks
             if t.get("status") == "pending" and set(t.get("depends_on", [])) <= done]
    lines += ["## Ready now", ""]
    if ready:
        by_id = {t.get("id"): t for t in tasks}
        for task in ready:
            lines.append(f"- `{task.get('id')}` {task.get('title', '')}")
            # Handoff notes of the tasks this one depends on, so a fresh session needs no old transcript
            for dep in task.get("depends_on", []):
                for note in by_id.get(dep, {}).get("handoff", []):
                    lines.append(f"  - from `{dep}`: {note}")
    else:
        lines.append("- none")
    lines.append("")

    groups = [
        ("Done", {"done"}),
        ("In progress", {"claimed", "in_progress", "verifying", "review", "rework"}),
        ("Blocked / failed", {"blocked", "failed"}),
        ("Open", {"pending"}),
    ]
    for title, statuses in groups:
        lines.append(f"## {title}")
        lines.append("")
        selected = [t for t in tasks if t.get("status") in statuses]
        if not selected:
            lines.append("- none")
        for task in selected:
            owner = task.get("owner") or "—"
            lines.append(
                f"- {ICONS.get(task.get('status'), '[ ]')} `{task.get('id')}` {task.get('title', '')} "
                f"— status: `{task.get('status')}` — owner: {owner}"
            )
        lines.append("")

    decisions = board.get("decisions", [])
    lines += ["## Decisions", ""]
    if decisions:
        for decision in decisions:
            date = decision.get("date", "—")
            did = decision.get("id", "ADR-?")
            title = decision.get("title", "")
            file = decision.get("file")
            suffix = f" (`{file}`)" if file else ""
            lines.append(f"- {date} `{did}` {title}{suffix}")
    else:
        lines.append("- none on the board; details in `docs/adr/`.")
    lines.append("")

    questions = [q for q in board.get("open_questions", []) if q.get("status", "open") == "open"]
    lines += ["## Open questions", ""]
    if questions:
        for question in questions:
            qid = question.get("id", "Q?")
            text = question.get("question", "")
            blocks = ", ".join(question.get("blocks", [])) or "—"
            status = question.get("status", "open")
            lines.append(f"- `{qid}` {text} — blocks: {blocks} — status: `{status}`")
    else:
        lines.append("- none on the board.")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", help="project folder containing board.json")
    parser.add_argument("--out", default="STATUS.md")
    args = parser.parse_args()

    root = Path(args.project).resolve()
    board = json.loads((root / "board.json").read_text(encoding="utf-8"))
    text = render(board)
    (root / args.out).write_text(text, encoding="utf-8")
    print(f"STATUS written: {root / args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
