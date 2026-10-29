#!/usr/bin/env python3
"""Generate STATUS.md and STATUS.html from board.json.

Usage:
    python3 tools/render_status.py examples/minimal-cli
    python3 tools/render_status.py examples/minimal-cli --out STATUS.md
    python3 tools/render_status.py examples/minimal-cli --html    # also STATUS.html
    python3 tools/render_status.py examples/minimal-cli --html --watch --interval 2

`--html` writes the same state as a self-contained web page: summary, stages,
every task with attempts, gate records, review verdict, tokens and audit
findings, the next wave, blocked tasks and pending approvals. 1.4 adds four
read-only views to that page: a Kanban board, a dependency graph, an activity
timeline and a token history, plus stage/package/owner filters. The page stays
one static file (inline CSS and one small inline filter script) and never
changes a status; `--watch` polls the stores and rewrites both pages atomically.
It shows token counts, which change every turn, so keep STATUS.html out of git.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
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
    if text.startswith("token budget"):
        return "token budget used"
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


# ---------------------------------------------------------------------------
# STATUS.html: the same state as a page, with tokens and evidence per task
# ---------------------------------------------------------------------------

HTML_CSS = """
:root{--bg:#f4f6f8;--card:#fff;--fg:#17212b;--muted:#5d6b78;--line:#d9e0e6;--accent:#d9731a;
--ok:#2f7d4f;--warn:#a86d0f;--bad:#b4372f;--info:#1f5f8b;--chip:#eef2f5}
@media (prefers-color-scheme:dark){:root{--bg:#121a22;--card:#19242f;--fg:#e2e9ee;--muted:#93a3b1;
--line:#2c3b48;--accent:#f08a2c;--ok:#6fc796;--warn:#e6b450;--bad:#f0786e;--info:#7fb3dc;--chip:#223140}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;padding:24px max(16px,env(safe-area-inset-left))}
main{max-width:1080px;margin:0 auto;display:flex;flex-direction:column;gap:22px}
header{display:flex;flex-direction:column;gap:4px;border-top:6px solid var(--accent);padding-top:14px}
h1{font-size:1.7rem;margin:0}h2{font-size:1.05rem;margin:0 0 10px}
.meta,.small{color:var(--muted);font-size:.88rem}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.tile b{display:block;font-size:1.6rem;font-variant-numeric:tabular-nums}
.tile span{color:var(--muted);font-size:.85rem}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px}
.wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:720px;font-size:.9rem}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:.72rem;letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
td.num{font-variant-numeric:tabular-nums;white-space:nowrap}tr:last-child td{border-bottom:0}
code{font:.85em ui-monospace,SFMono-Regular,Menlo,monospace}
.pill{display:inline-block;padding:1px 9px;border-radius:99px;font-size:.78rem;background:var(--chip);
border:1px solid var(--line);white-space:nowrap}
.done{color:var(--ok);border-color:var(--ok)}.blocked,.failed{color:var(--bad);border-color:var(--bad)}
.in_progress,.verifying,.review,.claimed{color:var(--info);border-color:var(--info)}
.rework{color:var(--warn);border-color:var(--warn)}
.bar{height:6px;border-radius:3px;background:var(--chip);overflow:hidden;margin-top:4px;min-width:80px}
.bar i{display:block;height:100%;background:var(--info)}.bar i.warn{background:var(--warn)}.bar i.over{background:var(--bad)}
ul.list{margin:0;padding-left:1.1em}ul.list li{margin:2px 0}
.stages{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
.stage{border:1px solid var(--line);border-radius:8px;padding:10px 12px}
/* 1.4 read-only views */
.filters{display:flex;flex-wrap:wrap;gap:10px;align-items:end;background:var(--card);
border:1px solid var(--line);border-radius:10px;padding:10px 14px}
.filters label{display:flex;flex-direction:column;gap:3px;font-size:.72rem;letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
.filters select{min-width:140px;padding:5px 7px;border:1px solid var(--line);border-radius:6px;
background:var(--card);color:var(--fg);font:inherit;font-size:.85rem}
.view-switch{display:flex}
input[name="view"]{position:absolute;opacity:0;pointer-events:none}
.view-switch label{padding:5px 15px;border:1px solid var(--line);background:var(--card);
color:var(--muted);cursor:pointer;font-size:.82rem}
.view-switch label:first-of-type{border-radius:7px 0 0 7px}
.view-switch label:last-of-type{border-radius:0 7px 7px 0;border-left:0}
#view-table:checked ~ .view-switch label[for="view-table"],
#view-kanban:checked ~ .view-switch label[for="view-kanban"]{background:var(--accent);border-color:var(--accent);color:#fff}
#view-kanban:checked ~ .views #tasks{display:none}
#view-table:checked ~ .views #kanban{display:none}
.kanban{display:flex;gap:10px;overflow-x:auto;padding-bottom:6px;align-items:flex-start}
.column{flex:1 1 130px;min-width:120px;background:var(--chip);border:1px solid var(--line);border-radius:8px;padding:8px;min-height:90px}
.column-head{display:flex;justify-content:space-between;align-items:baseline;padding:1px 3px 7px;
font-size:.7rem;letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
.column-head b{color:var(--fg)}
.card{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--muted);border-radius:7px;padding:8px;margin-bottom:7px}
.card.status-done{border-left-color:var(--ok)}
.card.status-blocked,.card.status-failed{border-left-color:var(--bad)}
.card.status-in_progress,.card.status-verifying,.card.status-review,.card.status-claimed{border-left-color:var(--info)}
.card.status-rework{border-left-color:var(--warn)}
.card-top{display:flex;justify-content:space-between;align-items:center;gap:6px}
.card-id{font:600 .8rem ui-monospace,SFMono-Regular,Menlo,monospace}
.card-title{font-size:.82rem;margin:4px 0 5px}
.card-meta{color:var(--muted);font-size:.72rem;display:flex;flex-wrap:wrap;gap:2px 8px}
.card-gates{color:var(--muted);font-size:.72rem;margin-top:4px}
.card .bar{min-width:0;margin-top:5px}
.card-token{color:var(--muted);font-size:.7rem;margin-top:2px}
.dep-graph{display:block;min-width:640px}
.stage-band{fill:var(--chip);opacity:.55}
.stage-name{fill:var(--muted);font-size:10px;letter-spacing:.07em;text-transform:uppercase}
.dep-edge{stroke:var(--muted);stroke-width:1.3;fill:none;opacity:.8}
.dep-edge.critical{stroke:var(--accent);stroke-width:2.4;opacity:1}
.node .node-box{fill:var(--card);stroke:var(--muted);stroke-width:1.3}
.node.status-done .node-box{stroke:var(--ok)}.node.status-done .node-id{fill:var(--ok)}
.node.status-blocked .node-box,.node.status-failed .node-box{stroke:var(--bad)}
.node.status-blocked .node-id,.node.status-failed .node-id{fill:var(--bad)}
.node.status-in_progress .node-box,.node.status-claimed .node-box,
.node.status-verifying .node-box,.node.status-review .node-box{stroke:var(--info)}
.node.status-in_progress .node-id,.node.status-claimed .node-id,
.node.status-verifying .node-id,.node.status-review .node-id{fill:var(--info)}
.node.status-rework .node-box{stroke:var(--warn)}.node.status-rework .node-id{fill:var(--warn)}
.node.status-pending .node-box{stroke:var(--muted)}
.node .node-id{font:600 10px ui-monospace,SFMono-Regular,Menlo,monospace}
.node .node-title{fill:var(--muted);font-size:9.5px}
.node.critical .node-box{stroke-width:2.8}
.node.cycle .node-box{stroke-dasharray:5 3}
.activity-table tr.gate-fail td{color:var(--bad)}
.tokens-wrap svg{display:block;width:100%;height:auto}
.token-line{fill:none;stroke-width:2}
.token-total{stroke:var(--fg);stroke-width:2.6}
.token-stage{opacity:.9}
.token-point{fill:var(--fg)}
.budget-line{stroke:var(--bad);stroke-width:1.4;stroke-dasharray:6 4}
.axis{stroke:var(--line)}
.axis-label{fill:var(--muted);font-size:10px}
.legend{display:flex;flex-wrap:wrap;gap:5px 14px;align-items:center;margin-top:10px;color:var(--muted);font-size:.78rem}
.legend .swatch{display:inline-block;width:20px;height:3px;background:var(--muted);vertical-align:middle;margin-right:4px}
.legend .swatch.critical{background:var(--accent)}
.legend .swatch.budget{background:var(--bad)}
.legend-swatch{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px;vertical-align:middle}
.warning{border-left:3px solid var(--warn);background:var(--chip);color:var(--fg);padding:8px 12px;border-radius:8px}
"""


def _esc(value) -> str:
    import html
    return html.escape("" if value is None else str(value))


def _tasks(board) -> list:
    raw = board.get("tasks") if isinstance(board, dict) else None
    return [task for task in raw if isinstance(task, dict)] if isinstance(raw, list) else []


def _task_id(task) -> str:
    value = task.get("id") if isinstance(task, dict) else None
    return value if isinstance(value, str) and value else "?"


STATUS_NAMES = ("pending", "claimed", "in_progress", "verifying", "review",
                "rework", "blocked", "failed", "done")

KANBAN_COLUMNS = (
    ("pending", "Pending", ("pending",)),
    ("in_progress", "In progress", ("claimed", "in_progress")),
    ("verifying", "Verifying", ("verifying",)),
    ("review", "Review", ("review",)),
    ("rework", "Rework", ("rework",)),
    ("blocked", "Blocked / failed", ("blocked", "failed")),
    ("done", "Done", ("done",)),
)

STAGE_COLORS = ("#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#a855f7", "#06b6d4")

FILTER_SCRIPT = """
/* Hide table rows and kanban cards that do not match the filters. Without
   JavaScript every row and card stays visible. */
(function () {
  var stage = document.getElementById('filter-stage');
  var pkg = document.getElementById('filter-package');
  var owner = document.getElementById('filter-owner');
  if (!stage || !pkg || !owner) { return; }
  function apply() {
    var rows = document.querySelectorAll('#tasks tbody tr, #kanban .card');
    for (var i = 0; i < rows.length; i += 1) {
      var row = rows[i];
      var ok = (!stage.value || row.getAttribute('data-stage') === stage.value)
        && (!pkg.value || row.getAttribute('data-package') === pkg.value)
        && (!owner.value || row.getAttribute('data-owner') === owner.value);
      row.style.display = ok ? '' : 'none';
    }
  }
  stage.addEventListener('change', apply);
  pkg.addEventListener('change', apply);
  owner.addEventListener('change', apply);
})();
"""


def _status_class(status) -> str:
    return status if status in STATUS_NAMES else "unknown"


def _effective_status(task) -> str:
    status = (task or {}).get("status")
    return status if status in STATUS_NAMES else "pending"


def _stage_ids(board) -> list:
    stages = board.get("stages") if isinstance(board, dict) else None
    if not isinstance(stages, list):
        return []
    return [stage.get("id") for stage in stages
            if isinstance(stage, dict) and isinstance(stage.get("id"), str)]


def _stage_label(board, task) -> str:
    value = (task or {}).get("stage")
    ids = _stage_ids(board)
    if isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if 1 <= value <= len(ids):
            return ids[value - 1]
        return f"Stage {value}"
    return "—"


def _stage_sort_key(board, label: str):
    ids = _stage_ids(board)
    if label in ids:
        return (0, ids.index(label), label)
    match = re.fullmatch(r"Stage ([0-9]+)", label or "")
    if match:
        return (1, int(match.group(1)), label)
    return (2, 0, label)


def _stage_labels_in_order(board) -> list:
    labels = [label for label in _stage_ids(board)]
    for task in _tasks(board):
        label = _stage_label(board, task)
        if label not in labels:
            labels.append(label)
    return sorted(labels, key=lambda label: _stage_sort_key(board, label))


def _package_label(task) -> str:
    value = (task or {}).get("package")
    return value if isinstance(value, str) and value else "—"


def _owner_label(task) -> str:
    value = (task or {}).get("owner")
    return value if isinstance(value, str) and value else "—"


def _attr(name: str, value) -> str:
    return f' {name}="{_esc(value)}"'


def _row_attrs(board, task) -> str:
    return (_attr("data-task", _task_id(task))
            + _attr("data-stage", _stage_label(board, task))
            + _attr("data-package", _package_label(task))
            + _attr("data-owner", _owner_label(task)))


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _parse_time(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone(dt.timezone.utc)


def _time_text(value) -> str:
    moment = _parse_time(value)
    if moment is None:
        return "—"
    return moment.strftime("%Y-%m-%d %H:%M:%S") + " UTC"


def _time_short(value) -> str:
    moment = _parse_time(value)
    if moment is None:
        return "—"
    return moment.strftime("%Y-%m-%d %H:%M")


def _time_order(value) -> float:
    moment = _parse_time(value)
    return float("-inf") if moment is None else moment.timestamp()


def _number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value >= 0:
        return int(value)
    return None


def _first_number(mapping, keys):
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        number = _number(mapping.get(key))
        if number is not None:
            return number
    return None


def _usage_tokens(data):
    """The token count of one usage event, tolerant of the common field names."""
    if not isinstance(data, dict):
        return None
    direct = _first_number(data, ("tokens", "total_tokens", "token_total", "total",
                                  "count", "n"))
    if direct is not None:
        return direct
    for left, right in (("input_tokens", "output_tokens"),
                        ("prompt_tokens", "completion_tokens"),
                        ("tokens_in", "tokens_out"),
                        ("input", "output"), ("in", "out")):
        first, second = _number(data.get(left)), _number(data.get(right))
        if first is not None or second is not None:
            return (first or 0) + (second or 0)
    nested = data.get("usage")
    if isinstance(nested, dict):
        return _usage_tokens(nested)
    return None


def _clean_event(event) -> dict:
    event = event if isinstance(event, dict) else {}
    data = event.get("data")
    kind = event.get("kind")
    return {
        "at": event.get("at") if isinstance(event.get("at"), str) else None,
        "kind": kind if isinstance(kind, str) and kind else "note",
        "data": data if isinstance(data, dict) else {},
    }


def _runs(root) -> list:
    """(task id, run record) for every readable file in runs/, usage included."""
    if root is None:
        return []
    folder = Path(root) / "runs"
    try:
        paths = sorted(folder.glob("*.json"))
    except OSError:
        return []
    try:
        from core.runs import load_run
    except Exception:  # noqa: BLE001
        load_run = None
    records = []
    for path in paths:
        record = None
        if load_run is not None:
            try:
                record = load_run(root, path.stem)
            except Exception:  # noqa: BLE001
                record = None
        if not isinstance(record, dict):
            record = _read_json(path)
        if not isinstance(record, dict):
            continue
        task = record.get("task")
        task = task if isinstance(task, str) and task else path.stem
        events = record.get("events")
        usage = record.get("usage")
        records.append((task, {
            "state": record.get("state"),
            "attempts": record.get("attempts") or [],
            "events": events if isinstance(events, list) else [],
            "usage": usage if isinstance(usage, dict) else {},
        }))
    return records


def _approvals(root) -> list:
    if root is None:
        return []
    try:
        from core.approvals import load_all
        return [record for record in load_all(root) if isinstance(record, dict)]
    except Exception:  # noqa: BLE001
        return []


def _usage_events(board, root) -> list:
    """Usage data points: the per-session usage store plus explicit usage events."""
    events = []
    for task_id, record in _runs(root):
        task = next((item for item in _tasks(board) if _task_id(item) == task_id), {})
        stage = _stage_label(board, task)
        for _key, entry in sorted(record["usage"].items()):
            if not isinstance(entry, dict):
                continue
            tokens = _number(entry.get("tokens"))
            if tokens is None:
                continue
            source = entry.get("source")
            events.append({"at": entry.get("updated"), "task": task_id,
                           "tokens": tokens, "stage": stage,
                           "actor": source if isinstance(source, str) and source else "—"})
        for event in record["events"]:
            clean = _clean_event(event)
            if clean["kind"] not in ("usage", "tokens", "token_usage"):
                continue
            tokens = _usage_tokens(clean["data"])
            if tokens is None:
                continue
            stage_value = clean["data"].get("stage")
            if isinstance(stage_value, int) and not isinstance(stage_value, bool):
                ids = _stage_ids(board)
                stage_value = ids[stage_value - 1] if 1 <= stage_value <= len(ids) else str(stage_value)
            event_stage = stage_value if isinstance(stage_value, str) and stage_value else stage
            actor = clean["data"].get("actor")
            events.append({"at": clean["at"], "task": task_id, "tokens": tokens,
                           "stage": event_stage,
                           "actor": actor if isinstance(actor, str) and actor else "—"})
    events.sort(key=lambda item: (_time_order(item["at"]), item["task"]))
    return events


def _token_budget(board, root=None):
    """The configured token budget: policy budget.max_tokens_per_task, then board keys."""
    candidates = []
    if root is not None:
        try:
            from core.policy import budget, load_policy
            candidates.append(budget(load_policy(root)).get("max_tokens_per_task"))
        except Exception:  # noqa: BLE001
            pass
        policy = _read_json(Path(root) / "policy.json")
        if isinstance(policy, dict):
            candidates.extend(policy.get(key) for key in ("token_budget", "budget", "tokens"))
    if isinstance(board, dict):
        budgets = board.get("budgets")
        if isinstance(budgets, dict):
            candidates.extend(budgets.get(key) for key in ("tokens", "token", "usage"))
        candidates.extend(board.get(key) for key in ("token_budget", "token_budget_total", "budget"))
    for candidate in candidates:
        if isinstance(candidate, dict):
            number = _first_number(candidate, ("tokens", "token", "limit", "max",
                                                "max_tokens", "max_tokens_per_task",
                                                "total", "budget"))
        else:
            number = _number(candidate)
        if number is not None and number > 0:
            return number
    return None


def _render_filters(board) -> str:
    tasks = _tasks(board)
    stages = []
    for task in tasks:
        label = _stage_label(board, task)
        if label not in stages:
            stages.append(label)
    stages.sort(key=lambda label: _stage_sort_key(board, label))
    packages = sorted({_package_label(task) for task in tasks})
    owners = sorted({_owner_label(task) for task in tasks})

    def options(values):
        return "".join(f'<option value="{_esc(value)}">{_esc(value)}</option>' for value in values)

    return ("<div class=\"filters\" id=\"filters\" aria-label=\"Task filters\">"
            "<label>Stage <select id=\"filter-stage\"><option value=\"\">All stages</option>"
            + options(stages) + "</select></label>"
            "<label>Package <select id=\"filter-package\"><option value=\"\">All packages</option>"
            + options(packages) + "</select></label>"
            "<label>Owner <select id=\"filter-owner\"><option value=\"\">All owners</option>"
            + options(owners) + "</select></label></div>")


def _render_kanban(board, checked, max_tokens, root) -> str:
    tasks = _tasks(board)
    usage = _usage_events(board, root)
    tokens: dict = {}
    for item in usage:
        tokens[item["task"]] = tokens.get(item["task"], 0) + item["tokens"]
    for task in tasks:
        task_id = _task_id(task)
        if task_id not in tokens:
            try:
                from core.runs import usage_total
                total = _number(usage_total(root, task_id))
            except Exception:  # noqa: BLE001
                total = None
            if total:
                tokens[task_id] = total
    max_seen = max(tokens.values()) if tokens else 0
    parts = ['<section id="kanban"><h2>Kanban</h2><div class="kanban">']
    for key, title, statuses in KANBAN_COLUMNS:
        selected = [task for task in tasks if _effective_status(task) in statuses]
        parts.append(f'<div class="column" data-status="{_esc(key)}">')
        parts.append(f'<div class="column-head"><span>{_esc(title)}</span>'
                     f'<b>{_esc(len(selected))}</b></div>')
        if not selected:
            parts.append('<p class="small">No tasks</p>')
        for task in selected:
            task_id = _task_id(task)
            info = checked.get(task_id, {})
            gates = info.get("gates") or [gate for gate in (task.get("gates") or [])
                                           if isinstance(gate, str)]
            passed = [gate for gate in gates if gate in (info.get("passed") or [])]
            used = tokens.get(task_id, 0)
            denominator = max_tokens or max_seen or 1
            share = min(100, used * 100 // denominator)
            level = ""
            if max_tokens:
                level = "over" if used >= max_tokens else ("warn" if share >= 80 else "")
            status = _effective_status(task)
            parts.append(f'<article class="card status-{_esc(_status_class(status))}"'
                         f'{_row_attrs(board, task)}>')
            parts.append(f'<div class="card-top"><span class="card-id">{_esc(task_id)}</span>'
                         f'<span class="pill {_esc(_status_class(status))}">{_esc(status)}</span></div>')
            parts.append(f'<div class="card-title">{_esc(task.get("title", ""))}</div>')
            parts.append(f'<div class="card-meta"><span>Stage: {_esc(_stage_label(board, task))}</span>'
                         f'<span>Owner: {_esc(_owner_label(task))}</span></div>')
            parts.append(f'<div class="card-gates">Gates {_esc(len(passed))}/{_esc(len(gates))}</div>')
            parts.append(f'<div class="bar" title="{_esc(f"{used:,} tokens")}">'
                         f'<i class="{_esc(level)}" style="width:{share}%"></i></div>')
            token_text = (f"{used:,} / {max_tokens:,} tok" if max_tokens
                          else (f"{used:,} tok" if used else "—"))
            parts.append(f'<div class="card-token">{_esc(token_text)}</div></article>')
        parts.append("</div>")
    parts.append("</div></section>")
    return "".join(parts)


# --- dependency graph ------------------------------------------------------

def _dependency_edges(board):
    tasks = _tasks(board)
    known = {_task_id(task) for task in tasks if _task_id(task) != "?"}
    edges = []
    unknown = []
    for task in tasks:
        task_id = _task_id(task)
        if task_id == "?":
            continue
        deps = task.get("depends_on")
        if not isinstance(deps, list):
            continue
        for dep in deps:
            if not isinstance(dep, str) or not dep:
                continue
            if dep in known:
                edges.append((dep, task_id))
            else:
                unknown.append((task_id, dep))
    return edges, unknown


def _adjacency(nodes, edges) -> dict:
    adjacency = {node: [] for node in nodes}
    for dep, task in edges:
        if dep in adjacency and task in adjacency and dep not in adjacency[task]:
            adjacency[task].append(dep)
    for node in adjacency:
        adjacency[node].sort()
    return adjacency


def _components(nodes, adjacency):
    """Strongly connected components (Kosaraju) and the component index per node."""
    order = []
    visited = set()
    for start in sorted(nodes):
        if start in visited:
            continue
        visited.add(start)
        stack = [(start, iter(sorted(adjacency.get(start, []))))]
        while stack:
            node, iterator = stack[-1]
            nxt = next(iterator, None)
            if nxt is None:
                order.append(node)
                stack.pop()
                continue
            if nxt in visited:
                continue
            visited.add(nxt)
            stack.append((nxt, iter(sorted(adjacency.get(nxt, [])))))
    reverse = {node: [] for node in nodes}
    for node in nodes:
        for dep in adjacency.get(node, []):
            reverse.setdefault(dep, []).append(node)
    assigned = {}
    components = []
    for node in reversed(order):
        if node in assigned:
            continue
        index = len(components)
        comp = []
        stack = [node]
        assigned[node] = index
        while stack:
            current = stack.pop()
            comp.append(current)
            for nxt in reverse.get(current, []):
                if nxt in nodes and nxt not in assigned:
                    assigned[nxt] = index
                    stack.append(nxt)
        components.append(comp)
    return components, assigned


def _cycle_members(nodes, adjacency):
    components, _assigned = _components(nodes, adjacency)
    members = set()
    cycles = []
    for component in components:
        cyclic = (len(component) > 1
                  or (bool(component) and component[0] in adjacency.get(component[0], [])))
        if cyclic:
            group = sorted(component)
            members.update(group)
            cycles.append(group)
    cycles.sort(key=lambda group: (len(group), group))
    return members, cycles


def _depths(nodes, adjacency):
    """Longest path from a root over the SCC condensation; one depth per node."""
    components, assigned = _components(nodes, adjacency)
    deps = {index: set() for index in range(len(components))}
    for node in nodes:
        own = assigned[node]
        for dep in adjacency.get(node, []):
            other = assigned.get(dep)
            if other is not None and other != own:
                deps[own].add(other)
    dependents = {index: set() for index in range(len(components))}
    for own, others in deps.items():
        for other in others:
            dependents[other].add(own)
    depth = {index: 0 for index in range(len(components))}
    indegree = {index: len(others) for index, others in deps.items()}
    queue = sorted(index for index in indegree if indegree[index] == 0)
    while queue:
        current = queue.pop(0)
        for nxt in sorted(dependents[current]):
            depth[nxt] = max(depth[nxt], depth[current] + 1)
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    node_depth = {node: depth[assigned[node]] for node in nodes}
    return node_depth, (max(node_depth.values()) if node_depth else 0)


def _critical_path(board, edges, excluded=None):
    excluded = excluded if isinstance(excluded, set) else set()
    nodes = sorted({_task_id(task) for task in _tasks(board)
                    if task.get("status") != "done"
                    and _task_id(task) not in excluded and _task_id(task) != "?"})
    if not nodes:
        return [], set()
    deps = {node: set() for node in nodes}
    dependents = {node: [] for node in nodes}
    for dep, task in edges:
        if dep in deps and task in deps and dep != task:
            deps[task].add(dep)
    for task, others in deps.items():
        for dep in others:
            dependents[dep].append(task)
    best = {node: (1, [node]) for node in nodes}
    indegree = {node: len(deps[node]) for node in nodes}
    queue = sorted(node for node in nodes if indegree[node] == 0)
    while queue:
        current = queue.pop(0)
        for nxt in sorted(dependents[current]):
            candidate = (best[current][0] + 1, best[current][1] + [nxt])
            if candidate > best[nxt]:
                best[nxt] = candidate
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    path = sorted(best.values(), key=lambda item: (-item[0], item[1]))[0][1]
    return path, set(zip(path, path[1:]))


def _clip(text, limit: int) -> str:
    text = text if isinstance(text, str) else ""
    return text if len(text) <= limit else text[:max(1, limit - 1)].rstrip() + "…"


def _render_dependency_graph(board) -> str:
    tasks = _tasks(board)
    by_id = {}
    nodes = []
    for task in tasks:
        task_id = _task_id(task)
        if task_id != "?" and task_id not in by_id:
            by_id[task_id] = task
            nodes.append(task_id)
    parts = ['<section id="graph"><h2>Dependency graph</h2>']
    if not nodes:
        parts.append('<p class="small">No tasks on the board.</p></section>')
        return "".join(parts)
    edges, unknown = _dependency_edges(board)
    adjacency = _adjacency(nodes, edges)
    cycle_nodes, cycles = _cycle_members(nodes, adjacency)
    node_depth, max_depth = _depths(nodes, adjacency)
    critical_nodes, critical_edges = _critical_path(board, edges, cycle_nodes)

    left, top, column_width, row_height = 150, 30, 190, 54
    node_width, node_height = 150, 38
    groups = []
    for label in _stage_labels_in_order(board):
        members = [node for node in nodes if _stage_label(board, by_id[node]) == label]
        if members:
            groups.append((label, members))
    positions = {}
    bands = []
    cursor = top
    for label, members in groups:
        members.sort(key=lambda node: (node_depth.get(node, 0), node))
        start = cursor
        for node in members:
            positions[node] = (left + node_depth.get(node, 0) * column_width, cursor)
            cursor += row_height
        bands.append((label, start, cursor))

    width = max(660, left + (max_depth + 1) * column_width + 20)
    height = cursor + 16
    parts.append('<div class="wrap"><svg class="dep-graph" viewBox="0 0 %d %d" role="img" '
                 'aria-label="Task dependency graph">' % (width, height))
    parts.append('<defs>'
                 '<marker id="dep-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" '
                 'markerHeight="7" orient="auto-start-reverse">'
                 '<path d="M0,0 L8,4 L0,8 z" fill="currentColor"/></marker></defs>')
    for label, start, end in bands:
        parts.append(f'<rect class="stage-band" x="0" y="{start - 6}" width="{width}" '
                     f'height="{max(1, end - start + 2)}" rx="6"/>')
        parts.append(f'<text class="stage-name" x="10" y="{start + 14}">{_esc(label)}</text>')
    for dep, task in edges:
        if dep not in positions or task not in positions:
            continue
        source_x, source_y = positions[dep]
        target_x, target_y = positions[task]
        if dep == task:
            x1 = x2 = source_x + node_width - 4
            y1, y2 = source_y + node_height - 4, source_y + 4
        elif source_x == target_x:
            x1 = x2 = source_x + node_width // 2
            y1, y2 = source_y + node_height, target_y
        else:
            x1, y1 = source_x + node_width, source_y + node_height // 2
            x2, y2 = target_x, target_y + node_height // 2
        critical = (dep, task) in critical_edges
        css = "dep-edge critical" if critical else "dep-edge"
        parts.append(f'<line class="{css}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                     f'data-from="{_esc(dep)}" data-to="{_esc(task)}" '
                     f'marker-end="url(#dep-arrow)"/>')
    for node in nodes:
        x, y = positions[node]
        task = by_id[node]
        status = task.get("status")
        css = f'node status-{_esc(_status_class(status))}'
        if node in cycle_nodes:
            css += " cycle"
        if node in critical_nodes:
            css += " critical"
        title = task.get("title", "")
        parts.append(f'<g class="{css}" data-task="{_esc(node)}" transform="translate({x},{y})">')
        parts.append(f'<rect class="node-box" width="{node_width}" height="{node_height}" rx="6"/>')
        parts.append(f'<text class="node-id" x="8" y="15">{_esc(node)}</text>')
        parts.append(f'<text class="node-title" x="8" y="29">{_esc(_clip(title, 20))}</text>')
        parts.append(f'<title>{_esc(node)} — {_esc(title)} ({_esc(status or "unknown")})</title>')
        parts.append("</g>")
    parts.append("</svg></div>")
    parts.append('<div class="legend">')
    for status in STATUS_NAMES:
        if any(by_id[node].get("status") == status for node in nodes):
            parts.append(f'<span class="pill {_esc(status)}">{_esc(status)}</span>')
    parts.append('<span><span class="swatch critical"></span>critical path</span>')
    if cycle_nodes:
        parts.append("<span>dashed border = dependency cycle</span>")
    parts.append("</div>")
    if cycles:
        groups_text = "; ".join(", ".join(cycle) for cycle in cycles)
        parts.append(f'<p class="warning">Dependency cycle involving: {_esc(groups_text)}. '
                     "The tasks on a cycle are marked in the graph; the board cannot be "
                     "laid out as a clean DAG.</p>")
    if critical_nodes:
        parts.append('<p class="small">Critical path (longest chain of unfinished tasks): '
                     + _esc(" → ".join(critical_nodes)) + "</p>")
    if unknown:
        shown = "; ".join(f"{task} depends on {dep}" for task, dep in unknown)
        parts.append(f'<p class="warning">Unknown dependency target: {_esc(shown)}.</p>')
    parts.append("</section>")
    return "".join(parts)


def _activity_rows(board, root) -> list:
    rows = []

    def add(at, task, kind, detail, actor, bad=False):
        rows.append({"at": at, "task": task, "kind": kind, "detail": detail,
                     "actor": actor, "bad": bad})

    for task_id, record in _runs(root):
        attempt = 0
        for event in record["events"]:
            clean = _clean_event(event)
            data = clean["data"]
            kind = clean["kind"]
            actor = data.get("actor") or data.get("by")
            actor = actor if isinstance(actor, str) and actor else "—"
            detail = ""
            bad = False
            if kind == "start":
                attempt += 1
                label = "start"
                detail = f"attempt {attempt}"
            elif kind == "gate":
                result = data.get("result")
                result_text = result if isinstance(result, str) else "?"
                label = f"gate {result_text}"
                detail = data.get("gate") if isinstance(data.get("gate"), str) else ""
                bad = result_text != "pass"
            elif kind == "state":
                label = "state"
                detail = f'{data.get("from", "?")} → {data.get("to", "?")}'
            elif kind in ("usage", "tokens", "token_usage"):
                label = "usage"
                tokens = _usage_tokens(data)
                detail = f"+{tokens:,} tokens" if tokens is not None else ""
            elif kind == "review":
                label = "review"
                verdict = data.get("verdict")
                round_no = data.get("round")
                detail = f"{verdict or '?'}" + (f" (round {round_no})" if round_no else "")
                bad = verdict == "fail"
            elif kind == "approval":
                label = "approval"
                detail = f'{data.get("action", "?")} {data.get("status", "?")}'
            elif kind == "note":
                label = "note"
                detail = _clip(data.get("note") or data.get("text") or "", 120)
            elif kind == "escalate":
                label = "escalate"
                detail = _clip(data.get("reason") or data.get("note") or "", 120)
            else:
                label = kind
                try:
                    detail = _clip(json.dumps(data, sort_keys=True), 120)
                except (TypeError, ValueError):
                    detail = _clip(str(data), 120)
            add(clean["at"], task_id, label, detail, actor, bad)
        for _key, entry in sorted(record["usage"].items()):
            if not isinstance(entry, dict):
                continue
            tokens = _number(entry.get("tokens"))
            if tokens is None:
                continue
            source = entry.get("source")
            actor = source if isinstance(source, str) and source else "—"
            add(entry.get("updated"), task_id, "usage", f"{tokens:,} tokens", actor)

    for record in _approvals(root):
        action = record.get("action")
        task = record.get("task") if isinstance(record.get("task"), str) else "—"
        requested_by = record.get("requested_by")
        add(record.get("requested_at"), task, "approval requested", action,
            requested_by if isinstance(requested_by, str) else "—")
        status = record.get("status")
        if status in ("granted", "denied") and record.get("approved_at"):
            approved_by = record.get("approved_by")
            add(record.get("approved_at"), task, f"approval {status}", action,
                approved_by if isinstance(approved_by, str) else "—")

    seen = set()
    unique = []
    for row in rows:
        key = (row["at"], row["task"], row["kind"], row["detail"], row["actor"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    unique.sort(key=lambda row: (_time_order(row["at"]), row["task"], row["kind"]),
                reverse=True)
    return unique[:50]


def _render_activity(board, root) -> str:
    rows = _activity_rows(board, root)
    parts = ['<section id="activity"><h2>Activity</h2>']
    if not rows:
        parts.append('<p class="small">No events recorded.</p></section>')
        return "".join(parts)
    parts.append('<div class="wrap"><table class="activity-table">')
    parts.append("<thead><tr><th>Time (UTC)</th><th>Task</th><th>Kind</th><th>Actor</th>"
                 "</tr></thead><tbody>")
    for row in rows:
        css = ' class="gate-fail"' if row["bad"] else ""
        detail = f' — {_esc(row["detail"])}' if row["detail"] else ""
        parts.append(f'<tr{css}><td class="num">{_esc(_time_text(row["at"]))}</td>'
                     f'<td><code>{_esc(row["task"])}</code></td>'
                     f'<td>{_esc(row["kind"])}{detail}</td>'
                     f'<td class="small">{_esc(row["actor"])}</td></tr>')
    parts.append("</tbody></table></div></section>")
    return "".join(parts)


def _render_token_history(board, root) -> str:
    usage = _usage_events(board, root)
    if not usage:
        return ""
    budget = _token_budget(board, root)
    times = [_parse_time(item["at"]) for item in usage]
    use_time = all(moment is not None for moment in times) and len(times) > 1
    span = (max(times) - min(times)).total_seconds() if use_time else 0.0
    use_time = use_time and span > 0

    chart_width, chart_height = 760, 260
    plot_left, plot_top, plot_right, plot_bottom = 62, 22, chart_width - 22, chart_height - 38
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top

    def x_at(sequence: int) -> float:
        if use_time:
            return plot_left + (times[sequence] - times[0]).total_seconds() / span * plot_width
        if len(usage) <= 1:
            return plot_left + plot_width / 2
        return plot_left + sequence / (len(usage) - 1) * plot_width

    cumulative = 0
    total_points = []
    stage_points = {}
    stage_totals = {}
    stage_order = []
    for sequence, item in enumerate(usage):
        cumulative += item["tokens"]
        total_points.append((sequence, cumulative))
        stage = item["stage"]
        if stage not in stage_points:
            stage_points[stage] = []
            stage_order.append(stage)
        stage_totals[stage] = stage_totals.get(stage, 0) + item["tokens"]
        stage_points[stage].append((sequence, stage_totals[stage]))
    y_max = max(cumulative, budget or 0, 1)

    def y_at(value: float) -> float:
        return plot_bottom - (value / y_max) * plot_height

    def points(pairs) -> str:
        return " ".join(f"{x_at(sequence):.1f},{y_at(value):.1f}"
                        for sequence, value in pairs)

    parts = ['<section id="tokens"><h2>Token history</h2><div class="wrap">']
    parts.append(f'<svg class="token-chart" viewBox="0 0 {chart_width} {chart_height}" role="img" '
                 'aria-label="Cumulative tokens over time">')
    parts.append(f'<line class="axis" x1="{plot_left}" y1="{plot_bottom}" '
                 f'x2="{plot_right}" y2="{plot_bottom}"/>')
    parts.append(f'<line class="axis" x1="{plot_left}" y1="{plot_top}" '
                 f'x2="{plot_left}" y2="{plot_bottom}"/>')
    parts.append(f'<text class="axis-label" x="{plot_left - 6}" y="{plot_bottom + 4}" '
                 'text-anchor="end">0</text>')
    parts.append(f'<text class="axis-label" x="{plot_left - 6}" y="{plot_top + 10}" '
                 f'text-anchor="end">{_esc(f"{y_max:,}")}</text>')
    parts.append(f'<text class="axis-label" x="{plot_left}" y="{chart_height - 12}">'
                 f'{_esc(_time_short(usage[0]["at"]))}</text>')
    parts.append(f'<text class="axis-label" x="{plot_right}" y="{chart_height - 12}" '
                 f'text-anchor="end">{_esc(_time_short(usage[-1]["at"]))}</text>')
    if budget:
        budget_y = y_at(budget)
        parts.append(f'<line class="budget-line" x1="{plot_left}" y1="{budget_y:.1f}" '
                     f'x2="{plot_right}" y2="{budget_y:.1f}"/>')
        parts.append(f'<text class="axis-label" x="{plot_right}" y="{budget_y - 4:.1f}" '
                     f'text-anchor="end">budget {_esc(f"{budget:,}")}</text>')
    parts.append(f'<polyline class="token-line token-total" points="{points(total_points)}"/>')
    for sequence, value in total_points:
        parts.append(f'<circle class="token-point" cx="{x_at(sequence):.1f}" '
                     f'cy="{y_at(value):.1f}" r="2.5"/>')
    for index, stage in enumerate(stage_order):
        color = STAGE_COLORS[index % len(STAGE_COLORS)]
        parts.append(f'<polyline class="token-line token-stage" '
                     f'points="{points(stage_points[stage])}" style="stroke:{color}"/>')
    parts.append("</svg>")
    parts.append('<div class="legend">')
    parts.append(f'<span><span class="legend-swatch" style="background:var(--fg)"></span>'
                 f'total {_esc(f"{cumulative:,}")}</span>')
    for index, stage in enumerate(stage_order):
        color = STAGE_COLORS[index % len(STAGE_COLORS)]
        parts.append(f'<span><span class="legend-swatch" style="background:{color}"></span>'
                     f'{_esc(stage)} {_esc(f"{stage_totals[stage]:,}")}</span>')
    if budget:
        parts.append(f'<span><span class="swatch budget"></span>budget {_esc(f"{budget:,}")}</span>')
    parts.append("</div></div></section>")
    return "".join(parts)


def _audit_entries(board, root) -> dict:
    try:
        from core.audit import audit
        return {entry["task"]: entry for entry in audit(Path(root), board)["tasks"]}
    except Exception:  # noqa: BLE001
        return {}


def _policy_max_tokens(root):
    try:
        from core.policy import budget, load_policy
        return budget(load_policy(Path(root)))["max_tokens_per_task"]
    except Exception:  # noqa: BLE001
        return None


def render_kanban(board, root=None) -> str:
    """The Kanban board fragment: seven columns, one card per task."""
    root = Path(root) if root is not None else None
    checked = _audit_entries(board, root) if root is not None else {}
    return _render_kanban(board, checked, _policy_max_tokens(root) if root else None, root)


def render_dependency_graph(board, root=None) -> str:
    """The inline-SVG dependency graph fragment with cycles, depth and critical path."""
    return _render_dependency_graph(board)


def render_activity(board, root=None) -> str:
    """The activity timeline fragment (run events and approvals, newest first)."""
    return _render_activity(board, root)


def render_token_history(board, root=None) -> str:
    """The token-history fragment, or "" when no usage data exists."""
    return _render_token_history(board, root)


def render_html(board: dict, root, watch: bool = False) -> str:
    """A self-contained STATUS.html: summary, stages, tasks, plan and the 1.4 views."""
    from core.audit import audit
    from core.dispatch import plan
    from core import runs as _runs
    root = Path(root)
    tasks = _tasks(board)
    try:
        report = plan(root, board)
    except Exception:  # noqa: BLE001  the page still renders without a plan
        report = {}
    try:
        checked = {entry["task"]: entry for entry in audit(root, board)["tasks"]}
    except Exception:  # noqa: BLE001
        checked = {}
    running = {entry.get("id"): entry for entry in report.get("running") or []}
    max_tokens = next((entry.get("max_tokens") for entry in running.values()), None)
    if max_tokens is None:
        try:
            from core.policy import budget, load_policy
            max_tokens = budget(load_policy(root))["max_tokens_per_task"]
        except Exception:  # noqa: BLE001
            max_tokens = None

    done = sum(1 for t in tasks if t.get("status") == "done")
    active = sum(1 for t in tasks if t.get("status") in ("in_progress", "verifying", "review", "rework"))
    blocked = report.get("blocked") or []
    pending = report.get("approvals_pending") or []
    tokens_total = 0
    rows = []
    for t in tasks:
        tid = str(t.get("id"))
        status = str(t.get("status"))
        info = checked.get(tid, {})
        try:
            used = _runs.usage_total(root, tid)
        except Exception:  # noqa: BLE001
            used = 0
        tokens_total += used
        gates = info.get("gates") or [g for g in t.get("gates") or [] if isinstance(g, str)]
        passed = [g for g in gates if g in (info.get("passed") or [])]
        verdict = (info.get("review") or {}).get("verdict")
        if max_tokens:
            share = min(100, used * 100 // max_tokens)
            level = "over" if used >= max_tokens else ("warn" if share >= 80 else "")
            token_cell = (f"{used:,}<div class='bar'><i class='{level}' style='width:{share}%'></i></div>")
        else:
            token_cell = f"{used:,}" if used else "–"
        findings = len(info.get("errors") or []) + len(info.get("warnings") or [])
        rows.append(
            f"<tr{_row_attrs(board, t)}><td><code>{_esc(tid)}</code></td>"
            f"<td>{_esc(t.get('title'))}</td>"
            f"<td><span class='pill {_esc(status)}'>{_esc(status)}</span></td>"
            f"<td class='num'>{info.get('attempts', 0)}/{info.get('max_attempts', '?')}</td>"
            f"<td class='num'>{len(passed)}/{len(gates)}</td>"
            f"<td>{_esc(verdict or '–')}</td><td class='num'>{token_cell}</td>"
            f"<td class='num'>{findings or '–'}</td></tr>")

    tiles = [(f"{done}/{len(tasks)}", "tasks done"), (str(active), "in progress"),
             (str(len(blocked)), "blocked"), (str(len(pending)), "approvals pending")]
    if tokens_total:
        tiles.append((f"{tokens_total:,}", "tokens recorded"))

    stages = stage_report(board, root) if board.get("stages") else []
    stage_html = ""
    if stages:
        cards = []
        for entry in stages:
            total = len(entry.get("tasks") or [])
            open_ = len(entry.get("tasks_open") or [])
            state = ("complete" if entry.get("complete") else "stopped" if entry.get("stopped")
                     else "waiting" if entry.get("incomplete_deps") else "open")
            cards.append(f"<div class='stage'><b>{_esc(entry.get('id'))}</b> "
                         f"<span class='small'>{_esc(entry.get('title'))}</span>"
                         f"<div class='small'>{state} · {total - open_}/{total} tasks done</div></div>")
        stage_html = (f"<section id=\"stages\"><h2>Stages</h2>"
                      f"<div class='stages'>{''.join(cards)}</div></section>")

    wave = ", ".join(f"<code>{_esc(i)}</code>" for i in report.get("next") or []) or "nothing is ready"
    blocked_html = "".join(f"<li><code>{_esc(b.get('id'))}</code> {_esc(b.get('reason'))}</li>"
                           for b in blocked) or "<li>none</li>"
    approvals_html = "".join(f"<li><code>{_esc(a.get('id'))}</code> {_esc(a.get('action'))}"
                             f"{' for ' + _esc(a.get('task')) if a.get('task') else ''}</li>"
                             for a in pending) or "<li>none</li>"
    budget_note = f"{max_tokens:,} tokens per task" if max_tokens else "no token budget"
    refresh = ('<meta http-equiv="refresh" content="5">' if watch else "")
    kanban = _render_kanban(board, checked, max_tokens, root)
    graph = _render_dependency_graph(board)
    activity = _render_activity(board, root)
    token_history = _render_token_history(board, root)
    token_section = token_history if token_history else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{refresh}
<title>{_esc(board.get('project') or 'Project')} status</title><style>{HTML_CSS}</style></head>
<body><main>
<header><h1>{_esc(board.get('project') or 'Project')}</h1>
<div class="meta">Profile {_esc(board.get('profile') or '?')} · {budget_note} · generated from board.json, runs/ and policy.json by Polier; do not edit by hand</div></header>
<div class="tiles">{''.join(f"<div class='tile'><b>{v}</b><span>{_esc(k)}</span></div>" for v, k in tiles)}</div>
{_render_filters(board)}
<input type="radio" name="view" id="view-table" checked>
<input type="radio" name="view" id="view-kanban">
<div class="view-switch"><label for="view-table">Table</label><label for="view-kanban">Kanban</label></div>
<div class="views">
<section id="tasks"><h2>Tasks</h2><div class="wrap"><table>
<thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Attempts</th><th>Gates</th><th>Review</th><th>Tokens</th><th>Findings</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></section>
{kanban}
</div>
{stage_html}
<section id="next"><h2>Next</h2><p>Next wave: {wave}</p></section>
<section id="blocked"><h2>Blocked</h2><ul class="list">{blocked_html}</ul></section>
<section id="approvals"><h2>Approvals pending</h2><ul class="list">{approvals_html}</ul></section>
{graph}
{activity}
{token_section}
<footer class="meta">Read-only page. Status changes only through tools/state.py;
everything here is regenerated from board.json, runs/, reviews/ and policy.json.</footer>
</main>
<script>{FILTER_SCRIPT}</script>
</body></html>
"""


# ---------------------------------------------------------------------------
# watch mode: poll the stores and rewrite both pages atomically
# ---------------------------------------------------------------------------

WATCHED = ("board.json", "runs", "reviews", "policy.json")


def watch_snapshot(root) -> dict:
    """mtime and size of board.json, runs/, reviews/ and policy.json, keyed by path."""
    folder = Path(root)
    snapshot = {}
    for name in WATCHED:
        path = folder / name
        try:
            if path.is_file():
                stat = path.stat()
                snapshot[name] = (stat.st_mtime_ns, stat.st_size)
            elif path.is_dir():
                for child in sorted(path.rglob("*")):
                    if not child.is_file():
                        continue
                    try:
                        stat = child.stat()
                    except OSError:
                        continue
                    snapshot[child.relative_to(folder).as_posix()] = (
                        stat.st_mtime_ns, stat.st_size)
        except OSError:
            continue
    return snapshot


def snapshot_changed(root, previous) -> bool:
    """True when the watched stores differ from `previous`; pure, no loop."""
    before = previous if isinstance(previous, dict) else {}
    return watch_snapshot(root) != before


def _atomic_write(path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _write_pages(root, board, html_name, md_name, watch_mode: bool) -> None:
    _atomic_write(Path(root) / html_name,
                  render_html(board, root, watch=watch_mode))
    _atomic_write(Path(root) / md_name, render(board, root, with_claims=True))


def watch(root, html_name="STATUS.html", md_name="STATUS.md", interval: float = 2.0) -> int:
    """Write both pages, then rewrite them whenever one of the stores changes."""
    folder = Path(root)
    try:
        pause = float(interval)
    except (TypeError, ValueError):
        pause = 2.0
    if pause <= 0:
        pause = 2.0
    previous = watch_snapshot(folder)
    board = _read_json(folder / "board.json")
    if not isinstance(board, dict):
        print(f"cannot read {folder / 'board.json'}", file=sys.stderr)
        return 2
    _write_pages(folder, board, html_name, md_name, True)
    print(f"STATUS watching: {folder / html_name}, {folder / md_name} (interval {pause:g}s)")
    while True:
        time.sleep(pause)
        current = watch_snapshot(folder)
        if current == previous:
            continue
        previous = current
        board = _read_json(folder / "board.json")
        if not isinstance(board, dict):
            continue  # a half-written board.json: keep the pages and retry
        try:
            _write_pages(folder, board, html_name, md_name, True)
        except Exception:  # noqa: BLE001  one bad render must not stop the watch
            continue
        print(f"STATUS updated: {folder / html_name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", help="project folder containing board.json")
    parser.add_argument("--out", default="STATUS.md")
    parser.add_argument("--html", nargs="?", const="STATUS.html", default=None, metavar="FILE",
                        help="also write the status as a web page (default STATUS.html)")
    parser.add_argument("--watch", action="store_true",
                        help="with --html: rewrite both pages whenever the stores change")
    parser.add_argument("--interval", type=float, default=2.0,
                        help="polling interval in seconds for --watch (default: 2)")
    args = parser.parse_args()

    if args.interval <= 0:
        parser.error("--interval must be a positive number of seconds")
    if args.watch and args.html is None:
        args.html = "STATUS.html"

    root = Path(args.project).resolve()
    try:
        board = json.loads((root / "board.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read {root / 'board.json'}: {exc}", file=sys.stderr)
        return 2

    if args.watch:
        try:
            return watch(root, args.html, args.out, args.interval)
        except KeyboardInterrupt:
            print("\nSTATUS watch stopped")
            return 0

    if args.html:
        (root / args.html).write_text(render_html(board, root), encoding="utf-8")
        print(f"STATUS page written: {root / args.html}")
    text = render(board, root, with_claims=True)
    (root / args.out).write_text(text, encoding="utf-8")
    print(f"STATUS written: {root / args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
