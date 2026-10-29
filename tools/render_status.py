#!/usr/bin/env python3
"""Generate STATUS.md from board.json.

Usage:
    python3 tools/render_status.py examples/minimal-cli
    python3 tools/render_status.py examples/minimal-cli --out STATUS.md
    python3 tools/render_status.py examples/minimal-cli --html    # also STATUS.html

`--html` writes the same state as a self-contained web page: summary, stages,
every task with attempts, gate records, review verdict, tokens and audit
findings, the next wave, blocked tasks and pending approvals. It shows token
counts, which change every turn, so keep STATUS.html out of git.
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
"""


def _esc(value) -> str:
    import html
    return html.escape("" if value is None else str(value))


def render_html(board: dict, root) -> str:
    """A self-contained STATUS.html: summary, stages, tasks with evidence and tokens, plan."""
    from core.audit import audit
    from core.dispatch import plan
    from core import runs as _runs
    root = Path(root)
    tasks = [t for t in board.get("tasks") or [] if isinstance(t, dict)]
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
            f"<tr><td><code>{_esc(tid)}</code></td><td>{_esc(t.get('title'))}</td>"
            f"<td><span class='pill {_esc(status)}'>{_esc(status)}</span></td>"
            f"<td class='num'>{info.get('attempts', 0)}/{info.get('max_attempts', '?')}</td>"
            f"<td class='num'>{len(passed)}/{len(gates)}</td>"
            f"<td>{_esc(verdict or '–')}</td><td class='num'>{token_cell}</td>"
            f"<td class='num'>{findings or '–'}</td></tr>")

    tiles = [(f"{done}/{len(tasks)}", "tasks done"), (str(active), "in progress"),
             (str(len(blocked)), "blocked"), (str(len(pending)), "approvals pending")]
    if tokens_total:
        tiles.append((f"{tokens_total:,}", "tokens recorded"))

    stage_html = ""
    stages = stage_report(board, root) if board.get("stages") else []
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
        stage_html = f"<section><h2>Stages</h2><div class='stages'>{''.join(cards)}</div></section>"

    wave = ", ".join(f"<code>{_esc(i)}</code>" for i in report.get("next") or []) or "nothing is ready"
    blocked_html = "".join(f"<li><code>{_esc(b.get('id'))}</code> {_esc(b.get('reason'))}</li>"
                           for b in blocked) or "<li>none</li>"
    approvals_html = "".join(f"<li><code>{_esc(a.get('id'))}</code> {_esc(a.get('action'))}"
                             f"{' for ' + _esc(a.get('task')) if a.get('task') else ''}</li>"
                             for a in pending) or "<li>none</li>"
    budget_note = f"{max_tokens:,} tokens per task" if max_tokens else "no token budget"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(board.get('project') or 'Project')} status</title><style>{HTML_CSS}</style></head>
<body><main>
<header><h1>{_esc(board.get('project') or 'Project')}</h1>
<div class="meta">Profile {_esc(board.get('profile') or '?')} · {budget_note} · generated from board.json, runs/ and policy.json by Polier; do not edit by hand</div></header>
<div class="tiles">{''.join(f"<div class='tile'><b>{v}</b><span>{_esc(k)}</span></div>" for v, k in tiles)}</div>
{stage_html}
<section><h2>Tasks</h2><div class="wrap"><table>
<thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Attempts</th><th>Gates</th><th>Review</th><th>Tokens</th><th>Findings</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></section>
<section><h2>Next</h2><p>Next wave: {wave}</p>
<h2 style="margin-top:12px">Blocked</h2><ul class="list">{blocked_html}</ul>
<h2 style="margin-top:12px">Approvals pending</h2><ul class="list">{approvals_html}</ul></section>
</main></body></html>
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", help="project folder containing board.json")
    parser.add_argument("--out", default="STATUS.md")
    parser.add_argument("--html", nargs="?", const="STATUS.html", default=None, metavar="FILE",
                        help="also write the status as a web page (default STATUS.html)")
    args = parser.parse_args()

    root = Path(args.project).resolve()
    board = json.loads((root / "board.json").read_text(encoding="utf-8"))
    if args.html:
        (root / args.html).write_text(render_html(board, root), encoding="utf-8")
        print(f"STATUS page written: {root / args.html}")
    text = render(board, root, with_claims=True)
    (root / args.out).write_text(text, encoding="utf-8")
    print(f"STATUS written: {root / args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
