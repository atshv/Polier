"""tools/render_status.py --html: the status as a self-contained web page."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import PACKAGE, run_tool

import render_status  # noqa: E402


class StatusPage(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="pl-html-")) / "proj"
        shutil.copytree(PACKAGE / "examples" / "monorepo-mini", self.root)
        self.addCleanup(shutil.rmtree, self.root.parent)

    def test_cli_writes_the_page_next_to_status(self):
        result = run_tool("render_status.py", str(self.root), "--html")
        self.assertEqual(result.returncode, 0, result.stderr)
        page = (self.root / "STATUS.html").read_text()
        self.assertTrue(page.startswith("<!doctype html>"))
        self.assertIn("<title>canvas-mini status</title>", page)
        self.assertIn("2/8", page)                       # tasks done
        self.assertIn("AP-001", page)                     # pending approval
        self.assertIn("waits for ENG-01", page)          # blocked with reason
        self.assertNotIn("<script src", page)             # no external script
        self.assertNotIn("<link", page)                   # no external stylesheet
        self.assertEqual(page.count("<script"), 1)        # only the small filter script
        self.assertIn('id="kanban"', page)
        self.assertIn('id="graph"', page)
        self.assertIn('id="activity"', page)
        self.assertTrue((self.root / "STATUS.md").is_file())

    def test_tokens_and_budget_are_shown(self):
        from core import runs
        runs.record_usage(self.root, "F-01", 1_900_000, session="s")
        page = render_status.render_html(json.loads((self.root / "board.json").read_text()), self.root)
        self.assertIn("2,000,000 tokens per task", page)
        self.assertIn("1,900,000", page)
        self.assertIn("class='warn'", page)

    def test_values_are_escaped(self):
        board = {"project": "<x>", "profile": "S", "tasks": [
            {"id": "M01", "title": "<script>alert(1)</script>", "status": "pending", "gates": []}]}
        page = render_status.render_html(board, self.root)
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;", page)


if __name__ == "__main__":
    unittest.main()
