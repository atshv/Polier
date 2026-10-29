"""tools/render_status.py: the read-only STATUS.html page on the 1.3 data model.

Covers the public HTML API (``render_html``, ``render_kanban``,
``render_dependency_graph``, ``render_activity``, ``render_token_history``), the
watch helpers and the ``--html`` / ``--watch`` CLI. Usage is synthetic: the 1.3
per-session store ``runs/<ID>.json["usage"]`` written through
``core.runs.record_usage`` plus one explicit ``usage`` event. Standard library
only; temporary projects are created with ``tempfile`` and removed in tearDown.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import PACKAGE, run_tool, task

import render_status
from core import runs

EXAMPLE = PACKAGE / "examples" / "monorepo-mini"

_TAG = re.compile(r"<([A-Za-z][-A-Za-z0-9]*)\b([^>]*)>")
_ATTR = re.compile(r'([A-Za-z_:][-A-Za-z0-9_:.]*)="([^"]*)"')
_CLASS = re.compile(r'class="([^"]*)"')


# ---------------------------------------------------------------------------
# HTML helpers: read attributes without depending on attribute order
# ---------------------------------------------------------------------------

def attributes(tag_text: str) -> dict:
    """The attributes of a single start tag, e.g. ``<article class="card" ...>``."""
    return dict(_ATTR.findall(tag_text))


def tags(text: str) -> list:
    """Every start tag of `text` as ``(name, attributes)``."""
    return [(name, attributes(attrs)) for name, attrs in _TAG.findall(text)]


def elements_with_class(text: str, token: str, name: str | None = None) -> list:
    """The attributes of every element whose class attribute has the exact class `token`."""
    found = []
    for tag_name, attrs in tags(text):
        if name is not None and tag_name != name:
            continue
        if token in attrs.get("class", "").split():
            found.append(attrs)
    return found


def cards(kanban: str) -> list:
    """The Kanban cards, one ``<article class="card" ...>`` per task."""
    return [attrs for attrs in elements_with_class(kanban, "card", "article")]


def table_body_rows(fragment: str) -> list:
    """The ``<tr>`` data rows inside ``<tbody>`` of an HTML table fragment."""
    body = re.search(r"(?is)<tbody>(.*?)</tbody>", fragment)
    if body is None:
        return []
    return re.findall(r"(?is)<tr\b[^>]*>.*?</tr>", body.group(1))


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def write_run(root: Path, tid: str, events: list) -> None:
    """Write ``runs/<tid>.json`` in the 1.3 run-record shape (events only)."""
    folder = root / "runs"
    folder.mkdir(exist_ok=True)
    record = {
        "task": tid,
        "state": "running",
        "attempt": 0,
        "attempts": [],
        "events": events,
        "usage": {},
        "updated": events[-1]["at"] if events else None,
    }
    (folder / f"{tid}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")


def write_approval(root: Path, record: dict) -> None:
    folder = root / "reviews" / "approvals"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{record['id']}.json").write_text(
        json.dumps(record, indent=2), encoding="utf-8")


class ProjectCase(unittest.TestCase):
    """Temporary projects; every fixture directory is removed after the test."""

    def project(self, tasks: list | None = None, project: str = "temp", **board_extra):
        root = Path(tempfile.mkdtemp(prefix="pl-html-"))
        self.addCleanup(shutil.rmtree, str(root), True)
        board = {"project": project, "profile": "S", "base_branch": "main",
                 "stage": 1, "tasks": list(tasks or [])}
        board.update(board_extra)
        (root / "board.json").write_text(json.dumps(board, indent=2), encoding="utf-8")
        return root, board

    def copied_example(self) -> Path:
        """A writable copy of examples/monorepo-mini (real 1.3 policy and stores)."""
        root = Path(tempfile.mkdtemp(prefix="pl-html-")) / "proj"
        shutil.copytree(EXAMPLE, root)
        self.addCleanup(shutil.rmtree, root.parent, True)
        return root

    @staticmethod
    def load_board(root: Path) -> dict:
        return json.loads((root / "board.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# the monorepo example: sections, assets, Kanban, dependency graph
# ---------------------------------------------------------------------------

class MonorepoExample(ProjectCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.board = json.loads((EXAMPLE / "board.json").read_text(encoding="utf-8"))
        cls.task_ids = [entry["id"] for entry in cls.board["tasks"]]

    def render(self, watch: bool = False) -> str:
        return render_status.render_html(self.board, EXAMPLE, watch=watch)

    def test_the_page_has_every_section_and_control(self):
        html = self.render()
        self.assertIsInstance(html, str)
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertIn("<html", html.lower())
        self.assertIn("</html>", html.lower())
        for section in ("tasks", "kanban", "stages", "next", "blocked",
                        "approvals", "graph", "activity"):
            self.assertIn(f'id="{section}"', html, f"missing section #{section}")
        # monorepo-mini has no usage records: the token history stays out.
        self.assertNotIn('id="tokens"', html)
        for control in ("filter-stage", "filter-package", "filter-owner"):
            self.assertIn(f'id="{control}"', html, f"missing filter #{control}")
        for view in ("view-table", "view-kanban"):
            self.assertIn(f'id="{view}"', html, f"missing view toggle #{view}")
        self.assertIsInstance(render_status.HTML_CSS, str)
        self.assertTrue(render_status.HTML_CSS.strip())
        self.assertIn("<style", html.lower())

    def test_the_page_loads_no_external_assets(self):
        """One self-contained document: no external assets, one small inline script."""
        html = self.render()
        for marker in ("http://", "https://", "<img", "@import", "javascript:"):
            self.assertNotIn(marker, html, f"the page must not reference {marker!r}")
        self.assertNotIn("<link", html.lower())
        self.assertNotRegex(html, r"(?i)<script[^>]*\bsrc=")
        scripts = re.findall(r"(?is)<script\b[^>]*>(.*?)</script>", html)
        self.assertEqual(len(scripts), 1, "exactly one inline script block is expected")
        code_lines = [line for line in scripts[0].splitlines() if line.strip()]
        self.assertLess(len(code_lines), 40, "the inline filter script must stay under 40 lines")

    def test_the_kanban_has_one_card_per_task(self):
        kanban = render_status.render_kanban(self.board, EXAMPLE)
        self.assertIn('id="kanban"', kanban)
        self.assertIn("<section", kanban.lower())
        found = cards(kanban)
        self.assertEqual(len(found), len(self.task_ids))
        self.assertEqual(sorted(attrs.get("data-task") for attrs in found),
                         sorted(self.task_ids))
        for attrs in found:
            # The card template carries the task, stage, package and owner.
            for name in ("data-task", "data-stage", "data-package", "data-owner"):
                self.assertIn(name, attrs, f"card is missing the {name} attribute")
        by_task = {attrs["data-task"]: attrs for attrs in found}
        self.assertEqual(by_task["ENG-01"]["data-package"], "packages/engine")
        self.assertEqual(by_task["F-01"]["data-owner"], "worker-1")
        self.assertEqual(by_task["F-01"]["data-stage"], "foundation")
        self.assertEqual(by_task["ENG-01"]["data-stage"], "engine-spike")

    def test_the_graph_has_one_edge_per_dependency(self):
        graph = render_status.render_dependency_graph(self.board, EXAMPLE)
        self.assertIn('id="graph"', graph)
        self.assertIn("<svg", graph.lower())
        edges = elements_with_class(graph, "dep-edge")
        expected = sum(len(entry.get("depends_on") or []) for entry in self.board["tasks"])
        self.assertEqual(expected, 12)  # guard the fixture itself
        self.assertEqual(len(edges), expected)
        nodes = elements_with_class(graph, "node", "g")
        self.assertEqual(len(nodes), len(self.task_ids))
        self.assertEqual(sorted(attrs.get("data-task") for attrs in nodes),
                         sorted(self.task_ids))


# ---------------------------------------------------------------------------
# temporary projects: empty stores, cycles, escaping, activity, tokens
# ---------------------------------------------------------------------------

class TempProjects(ProjectCase):
    def test_a_project_without_runs_renders_activity_without_tokens(self):
        root, board = self.project([task("T1", status="pending")])
        html = render_status.render_html(board, root)
        self.assertIn('id="activity"', html)
        self.assertNotIn('id="tokens"', html)
        self.assertEqual(render_status.render_token_history(board, root), "")
        # A run record without usage data still never shows a token history.
        runs.append_event(root, "T1", "start", {"actor": "lead"},
                          at="2026-10-25T01:00:00+00:00")
        self.assertEqual(render_status.render_token_history(board, root), "")
        self.assertIn('id="activity"', render_status.render_activity(board, root))

    def test_a_dependency_cycle_renders_with_a_cycle_warning(self):
        board_tasks = [task("A", status="pending", depends_on=["B"]),
                       task("B", status="pending", depends_on=["C"]),
                       task("C", status="pending", depends_on=["A"])]
        root, board = self.project(board_tasks)
        html = render_status.render_html(board, root)  # must not raise or hang
        self.assertRegex(html, r"(?i)dependency cycle")
        graph = render_status.render_dependency_graph(board, root)
        self.assertEqual(len(elements_with_class(graph, "dep-edge")), 3)
        for tid in ("A", "B", "C"):
            nodes = [attrs for attrs in elements_with_class(graph, "node", "g")
                     if attrs.get("data-task") == tid]
            self.assertTrue(nodes, f"missing graph node {tid}")
            self.assertIn("cycle", nodes[0].get("class", "").split(),
                          f"node {tid} is not marked as a cycle member")

    def test_a_chorded_cycle_marks_every_member(self):
        """A deps [B,C], B deps [A], C deps [B]: all three belong to one SCC."""
        board_tasks = [task("A", status="pending", depends_on=["B", "C"]),
                       task("B", status="pending", depends_on=["A"]),
                       task("C", status="pending", depends_on=["B"])]
        root, board = self.project(board_tasks)
        graph = render_status.render_dependency_graph(board, root)  # must not raise
        self.assertEqual(len(elements_with_class(graph, "dep-edge")), 4)
        nodes = {attrs.get("data-task"): attrs
                 for attrs in elements_with_class(graph, "node", "g")}
        self.assertEqual(sorted(nodes), ["A", "B", "C"])
        for tid in ("A", "B", "C"):
            classes = nodes[tid].get("class", "").split()
            self.assertIn("cycle", classes, f"node {tid} is not marked as a cycle member")
            self.assertNotIn("critical", classes,
                             f"cycle member {tid} must not be on the critical path")
        warning = re.search(r'(?is)<p class="warning">(.*?)</p>', graph)
        self.assertIsNotNone(warning, "the graph must warn about the cycle")
        warning_text = warning.group(1)
        self.assertRegex(warning_text, r"(?i)dependency cycle")
        for tid in ("A", "B", "C"):
            self.assertRegex(warning_text, rf"\b{tid}\b",
                             f"the cycle warning does not name {tid}")
        # SCC members are excluded from the critical path: no ordinary path line.
        self.assertNotIn("Critical path", graph)
        for edge in elements_with_class(graph, "dep-edge"):
            self.assertNotIn("critical", edge.get("class", "").split())

    def test_task_titles_and_project_names_are_escaped(self):
        root, board = self.project(
            [task("T1", title="<script>alert('x')</script>")],
            project="Q&A & Co")
        html = render_status.render_html(board, root)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>alert", html)
        self.assertIn("&amp;", html)
        self.assertIn("Q&amp;A", html)
        self.assertNotIn("Q&A", html)  # the raw ampersand form is gone

    def test_a_failed_gate_is_marked_in_the_activity(self):
        root, board = self.project([task("T1", status="in_progress")])
        runs.append_event(root, "T1", "gate",
                          {"gate": "tests", "result": "fail"}, at="2026-10-25T01:05:16+00:00")
        write_approval(root, {
            "id": "AP-001", "action": "new_dependency", "task": "T1",
            "status": "pending", "requested_by": "lead",
            "requested_at": "2026-10-25T01:30:00+00:00",
            "approved_by": None, "approved_at": None, "note": "adds httpx",
        })
        activity = render_status.render_activity(board, root)
        self.assertIn('id="activity"', activity)
        # The timeline merges both stores: the approval request is listed with
        # its action, next to the run-record gate event.
        self.assertIn("approval requested", activity)
        self.assertIn("new_dependency", activity)
        self.assertIn("gate fail", activity)
        self.assertGreaterEqual(len(elements_with_class(activity, "gate-fail")), 1)
        # Newest first: the approval (01:30) comes before the gate (01:05).
        self.assertLess(activity.index("approval requested"), activity.index("gate fail"))

    def test_the_activity_keeps_the_newest_fifty_rows(self):
        root, board = self.project([task("T1", status="in_progress")])
        events = [{"at": f"2026-10-25T01:{minute:02d}:00+00:00", "kind": "start",
                   "data": {"actor": "lead"}} for minute in range(60)]
        write_run(root, "T1", events)
        activity = render_status.render_activity(board, root)
        rows = table_body_rows(activity)
        self.assertEqual(len(rows), 50, "the timeline is capped at 50 rows")
        times = []
        for row in rows:
            match = re.search(r"(\d{2}):(\d{2}):(\d{2})", row)
            self.assertIsNotNone(match, f"row has no timestamp: {row}")
            times.append(match.group(0))
        self.assertEqual(times[0], "01:59:00", "the newest event comes first")
        self.assertEqual(times[-1], "01:10:00", "the 50 newest events are kept")
        self.assertEqual(times, sorted(times, reverse=True), "rows must be newest first")

    def test_the_token_history_uses_the_per_session_usage_store(self):
        """Usage from runs/<ID>.json["usage"] (record_usage) plus one explicit event."""
        root = self.copied_example()
        runs.record_usage(root, "F-01", 1_900_000, session="s1")
        runs.record_usage(root, "ENG-01", 250_000, session="s1")
        runs.append_event(root, "F-02", "usage",
                          {"tokens": 300, "stage": "foundation", "actor": "worker-1"},
                          at="2026-10-25T01:30:00+00:00")
        board = self.load_board(root)
        tokens = render_status.render_token_history(board, root)
        self.assertTrue(tokens.strip(), "usage records must render a token history")
        for marker in ('id="tokens"', "token-total", "token-stage", "budget-line"):
            self.assertIn(marker, tokens)
        self.assertIn("<polyline", tokens.lower())
        # The 1.3 policy budget (2,000,000 per task) is shown on the page too.
        html = render_status.render_html(board, root)
        self.assertIn('id="tokens"', html)
        self.assertIn("2,000,000 tokens per task", html)
        self.assertIn("1,900,000", html)

    def test_a_token_budget_on_the_board_is_used(self):
        root, board = self.project(
            [task("T1", status="done", stage="foundation")],
            budgets={"tokens": {"limit": 1200}})
        runs.append_event(root, "T1", "usage",
                          {"tokens": 400, "stage": "foundation", "actor": "worker-1"},
                          at="2026-10-25T01:00:00+00:00")
        tokens = render_status.render_token_history(board, root)
        self.assertIn('id="tokens"', tokens)
        self.assertIn("token-total", tokens)
        self.assertIn("token-stage", tokens)
        self.assertIn("budget-line", tokens)


# ---------------------------------------------------------------------------
# watch helpers and the CLI
# ---------------------------------------------------------------------------

class WatchAndCli(ProjectCase):
    def test_the_watch_snapshot_detects_changes_without_a_loop(self):
        root, _board = self.project([task("T1")])
        (root / "runs").mkdir()
        snapshot = render_status.watch_snapshot(root)
        self.assertIsInstance(snapshot, dict)
        self.assertFalse(render_status.snapshot_changed(root, snapshot))
        self.assertFalse(render_status.snapshot_changed(root, snapshot))  # pure read

        # A new run record changes the snapshot.
        (root / "runs" / "X.json").write_text("{}", encoding="utf-8")
        self.assertTrue(render_status.snapshot_changed(root, snapshot))

        # A touched board.json changes it too.
        snapshot = render_status.watch_snapshot(root)
        board_path = root / "board.json"
        stat = board_path.stat()
        os.utime(board_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        self.assertTrue(render_status.snapshot_changed(root, snapshot))

    def test_the_html_cli_writes_the_page_and_the_markdown(self):
        root, _board = self.project([task("T1")])
        result = run_tool("render_status.py", str(root), "--html")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        page = root / "STATUS.html"
        self.assertTrue(page.is_file())
        text = page.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("<!doctype html>"))
        self.assertNotIn('http-equiv="refresh"', text)
        self.assertTrue((root / "STATUS.md").is_file())
        # --html takes an optional FILE name.
        result = run_tool("render_status.py", str(root), "--html", "page.html")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((root / "page.html").is_file())

    def test_watch_mode_adds_the_refresh_meta_tag(self):
        root, board = self.project([task("T1")])
        watch_html = render_status.render_html(board, root, watch=True)
        match = re.search(r'(?i)<meta[^>]*http-equiv="refresh"[^>]*>', watch_html)
        self.assertIsNotNone(match, "watch=True must add the refresh meta tag")
        self.assertIn('content="5"', match.group(0))
        plain_html = render_status.render_html(board, root)
        self.assertNotRegex(plain_html, r'(?i)http-equiv="refresh"')


if __name__ == "__main__":
    unittest.main()
