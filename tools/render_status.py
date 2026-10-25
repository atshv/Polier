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


def _stage_key(stage) -> str:
    return f"stage:{stage}" if isinstance(stage, int) else f"id:{stage}"


def _render_stages(board: dict, tasks: list, stages: list) -> list:
    """Per declared stage: title, tasks, exit criteria, exit gates, owner decision."""
    if not stages:
        return []
    lines = ["## Stages", ""]
    for index, stage in enumerate(stages, 1):
        sid = stage.get("id", f"S{index}")
        title = stage.get("title", "")
        decision = stage.get("owner_decision", "pending")
        members = [t.get("id") for t in tasks if _stage_key(t.get("stage")) == _stage_key(sid)]
        lines.append(f"### Stage {index} — `{sid}` {title}".rstrip())
        lines.append("")
        lines.append(f"- Owner decision: `{decision}`")
        if members:
            lines.append(f"- Tasks: {', '.join(str(m) for m in members)}")
        criteria = [c for c in stage.get("exit_criteria", []) if isinstance(c, str)]
        if criteria:
            lines.append("- Exit criteria: " + "; ".join(criteria))
        gates = [g for g in stage.get("exit_gates", []) if isinstance(g, str)]
        if gates:
            lines.append("- Exit gates: " + ", ".join(f"`{g}`" for g in gates))
        lines.append("")
    return lines


def _render_packages(board: dict) -> list:
    packages = board.get("packages")
    if not isinstance(packages, list) or not packages:
        return []
    lines = ["## Packages", ""]
    for package in packages:
        if not isinstance(package, dict):
            continue
        path = package.get("path", "?")
        kind = package.get("kind", "?")
        may = ", ".join(p for p in package.get("may_import", []) if isinstance(p, str)) or "—"
        lines.append(f"- `{path}` — kind: `{kind}` — may import: {may}")
    lines.append("")
    return lines


def _render_runtime(board: dict) -> list:
    resources = board.get("resources")
    if not isinstance(resources, dict):
        return []
    slots = resources.get("slots", 3)
    base = resources.get("port_base", 4000)
    stride = resources.get("port_stride", 100)
    services = resources.get("services")
    lines = ["## Runtime", ""]
    lines.append(f"- Slots: {slots} (0 = main checkout) · ports: {base} + {stride}·N")
    if isinstance(services, dict) and services:
        offsets = ", ".join(f"{name} +{offset}" for name, offset in services.items())
        lines.append(f"- Services: {offsets}")
    lines.append("- Ports, database and bucket names: read `.polier-slot` (`tools/slot.py show`)")
    lines.append("")
    return lines



def render(board: dict) -> str:
    tasks = board.get("tasks", [])
    stages = [s for s in board.get("stages", []) if isinstance(s, dict)] \
        if isinstance(board.get("stages"), list) else []
    task_stages = [t.get("stage", 1) for t in tasks if isinstance(t.get("stage"), int)]
    stage = board.get("stage", 1)
    if not isinstance(stage, int):
        stage = 1
    max_stage = max(task_stages + [stage]) if task_stages else stage
    if stages:
        max_stage = max(max_stage, len(stages))
    if stages:
        stage_line = f"**Stage:** {stage} of {max_stage} ({len(stages)} defined)"
    else:
        stage_line = f"**Stage:** {stage} of {max_stage}"

    lines = [
        "# Status",
        "",
        f"**Project:** {board.get('project', '?')} · **Profile:** {board.get('profile', '?')} · {stage_line}",
        "",
        "> Generated from `board.json`. Do not edit by hand.",
        "",
    ]

    lines += _render_stages(board, tasks, stages)
    lines += _render_packages(board)
    lines += _render_runtime(board)

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
