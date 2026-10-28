#!/usr/bin/env python3
"""Generate STATUS.md from board.json.

Usage:
    python3 tools/render_status.py examples/minimal-cli
    python3 tools/render_status.py examples/minimal-cli --out STATUS.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.board import ready_tasks, stage_report  # noqa: E402

# Live task claims (PL-04) are shown inside these markers. They change every
# few minutes, so tools/check.py ignores the block when it compares STATUS.md
# with a fresh render.
CLAIMS_BEGIN = "<!-- polier:claims -->"
CLAIMS_END = "<!-- /polier:claims -->"

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


def _render_stages(board: dict, tasks: list, root=None) -> list:
    """Per declared stage: state, owner decision, exit gates, exit criteria, tasks."""
    report = stage_report(board, root)
    if not report:
        return []
    lines = ["## Stages", ""]
    for stage in report:
        lines.append(f"### Stage {stage['index']} — `{stage['id']}` {stage['title']}".rstrip())
        lines.append("")
        if stage["stopped"]:
            state = "stopped by the owner"
        elif stage["owner_pending"]:
            state = "waiting for the owner decision"
        elif stage["missing_gates"]:
            state = "exit gates missing: " + ", ".join(stage["missing_gates"])
        elif stage["incomplete_deps"]:
            state = "blocked by stage " + ", ".join(stage["incomplete_deps"])
        elif stage.get("tasks_open"):
            state = "tasks open"
        else:
            state = "complete"
        lines.append(f"- State: {state}")
        lines.append(f"- Owner decision: `{stage['owner_decision']}`")
        if stage["exit_gates"]:
            shown = [f"`{g}`" + (" (missing record)" if g in stage["missing_gates"] else "")
                     for g in stage["exit_gates"]]
            lines.append("- Exit gates: " + ", ".join(shown))
        if stage["exit_criteria"]:
            lines.append("- Exit criteria: " + "; ".join(stage["exit_criteria"]))
        if stage["tasks"]:
            lines.append("- Tasks: " + ", ".join(str(t) for t in stage["tasks"]))
        if stage.get("tasks_open"):
            lines.append("- Tasks open: " + ", ".join(str(t) for t in stage["tasks_open"]))
        lines.append("")
    return lines


def _render_claims(root) -> list:
    """Live claims of every harness: "in progress by <harness> since <time>" (PL-04)."""
    if root is None:
        return []
    try:
        from core.claims import live_claims
        claims = live_claims(root)
    except Exception:  # noqa: BLE001  no claims support or no git repo: stay silent
        return []
    if not claims:
        return []
    lines = [CLAIMS_BEGIN, "## Claims", ""]
    for claim in claims:
        parts = [f"- `{claim.get('task')}` in progress by {claim.get('harness')}",
                 f"since {claim.get('heartbeat', claim.get('started', '?'))}"]
        if claim.get("worktree"):
            parts.append(f"— worktree: {claim['worktree']}")
        if claim.get("slot") is not None:
            parts.append(f"· slot {claim['slot']}")
        lines.append(" ".join(parts))
    lines += ["", CLAIMS_END, ""]
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



def _short_blocked_reason(reason) -> str:
    """One of the dispatch reasons, shortened for the one-line STATUS budget."""
    text = reason.strip() if isinstance(reason, str) else ""
    if text.startswith("attempts "):
        return "attempts exhausted"
    if "stage stopped" in text:
        return "stopped stage"
    if text.startswith("stage waits"):
        return "stage waits"
    if text.startswith("waits for"):
        return "open dependency"
    if "brief" in text and "missing" in text:
        return "missing brief"
    if text.startswith("claimed by"):
        return "claimed by another session"
    return text


def _render_orchestration(board: dict, root, with_claims: bool) -> list:
    """The 1.1 execution state in at most 10 lines: limits, next wave, running, blocked, approvals.

    Rendered only when the project uses the 1.1 stores (a policy or run
    records). The running-task claim is shown inside the claims markers, so the
    freshness check stays stable while sessions come and go.
    """
    if root is None:
        return []
    folder = Path(root)
    if not (folder / "policy.json").is_file() and not (folder / "runs").is_dir():
        return []
    try:
        from core.dispatch import plan
        report = plan(folder, board)
    except Exception:  # noqa: BLE001  a broken plan must not stop the render
        return []

    limits = report.get("limits") or {}
    lines = ["## Orchestration", ""]
    lines.append(f"- Limits: {limits.get('max_attempts_per_task', '?')} attempts/task, "
                 f"{limits.get('max_in_progress', '?')} in progress")

    next_ids = [str(task) for task in report.get("next") or []]
    if next_ids:
        lines.append("- Next wave: " + ", ".join(f"`{tid}` ({'tasks/' + tid + '.md'})"
                                                 for tid in next_ids))
    else:
        lines.append("- Next wave: none — nothing is ready")

    running = report.get("running") or []
    if running:
        parts = []
        for entry in running:
            text = (f"`{entry.get('id')}` attempt {entry.get('attempt', 0)}"
                    f"/{entry.get('max_attempts') or '?'}")
            claim = entry.get("claim")
            if isinstance(claim, dict) and with_claims:
                harness = claim.get("harness") or "unknown harness"
                text += f"{CLAIMS_BEGIN} — claimed by {harness}{CLAIMS_END}"
            parts.append(text)
        lines.append("- Running: " + "; ".join(parts))
    else:
        lines.append("- Running: none")

    blocked = report.get("blocked") or []
    if blocked:
        groups: dict = {}
        for entry in blocked:
            groups.setdefault(_short_blocked_reason(entry.get("reason")), []).append(
                str(entry.get("id")))
        lines.append("- Blocked: " + "; ".join(
            f"{', '.join(ids)} ({reason})" for reason, ids in groups.items()))
    else:
        lines.append("- Blocked: none")

    pending = report.get("approvals_pending") or []
    if pending:
        parts = []
        for record in pending:
            target = f" for {record.get('task')}" if record.get("task") else ""
            parts.append(f"`{record.get('id')}` {record.get('action')}{target}")
        lines.append("- Approvals pending: " + "; ".join(parts))
    else:
        lines.append("- Approvals pending: none")

    lines.append("")
    return lines


def strip_claims(text: str) -> str:
    """`text` without the live-claims block, for the STATUS.md freshness check."""
    without = re.sub(re.escape(CLAIMS_BEGIN) + r".*?" + re.escape(CLAIMS_END), "", text, flags=re.S)
    return re.sub(r"\n{3,}", "\n\n", without)


def render(board: dict, root=None, with_claims: bool = True) -> str:
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

    lines += _render_stages(board, tasks, root)
    lines += _render_packages(board)
    lines += _render_runtime(board)

    # Ready now: pending tasks whose dependencies are done and blocking stages complete
    ready = ready_tasks(board, root)
    lines += ["## Ready now", ""]
    if ready:
        for task in ready:
            lines.append(f"- `{task['id']}` {task.get('title', '')}")
            for note in task.get("handoff", []):
                lines.append(f"  - {note}")
    else:
        lines.append("- none")
    lines.append("")

    # 1.1 execution state: limits, next wave, running, blocked, pending approvals.
    lines += _render_orchestration(board, root, with_claims)

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

    if with_claims:
        lines += _render_claims(root)

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
    text = render(board, root, with_claims=True)
    (root / args.out).write_text(text, encoding="utf-8")
    print(f"STATUS written: {root / args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
