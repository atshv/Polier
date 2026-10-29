"""core/dashboard.py: the read models behind the dashboard API."""
from __future__ import annotations

import json
import unittest

from dash_helpers import PACKAGE, sample_project

from core import dashboard, paths
from core.errors import PolierError


class DashboardDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = sample_project()

    def test_snapshot_has_board_execution_and_dispatch(self) -> None:
        snap = dashboard.snapshot(self.root)
        self.assertEqual(snap["schema"], dashboard.DASHBOARD_SCHEMA)
        self.assertEqual(snap["project"]["name"], "canvas-mini")
        self.assertEqual(len(snap["tasks"]), 8)
        self.assertTrue(snap["stages"])
        self.assertIn("waves", snap["dispatch"])
        self.assertTrue(snap["git"]["head"])
        self.assertIn("packages", snap["project"])
        self.assertTrue(snap["project"]["packages"])
        by_id = {task["id"]: task for task in snap["tasks"]}
        done = by_id["F-01"]
        self.assertEqual(done["status"], "done")
        self.assertTrue(done["review"]["present"])
        self.assertEqual(done["review"]["verdict"], "pass")
        self.assertTrue(done["gates_passed"])
        self.assertEqual(done["gates_missing"], [])
        self.assertIn("tokens", done)
        self.assertIn("budget", done)
        self.assertIsInstance(snap["counts"].get("done"), int)

    def test_task_view_marks_ready_and_blocked(self) -> None:
        snap = dashboard.snapshot(self.root)
        by_id = {task["id"]: task for task in snap["tasks"]}
        ready = [task for task in snap["tasks"] if task["ready"]]
        blocked = [task for task in snap["tasks"] if task["blocked_reason"]]
        self.assertTrue(ready or blocked)
        for task in ready:
            self.assertIsNone(task["blocked_reason"])
        for task in blocked:
            self.assertIsNotNone(task["blocked_reason"])

    def test_task_detail_contains_texts_and_events(self) -> None:
        detail = dashboard.task_detail(self.root, "F-01")
        self.assertEqual(detail["task"]["id"], "F-01")
        self.assertTrue(detail["brief"]["text"])
        self.assertTrue(detail["review"]["text"])
        self.assertIn("events", detail)
        self.assertIn("gate_records", detail)
        self.assertTrue(detail["gate_logs"])
        self.assertTrue(detail["gate_logs"][0]["present"])

    def test_activity_is_newest_first(self) -> None:
        items = dashboard.activity(self.root, 50)
        self.assertTrue(items)
        stamps = [str(item["at"]) for item in items]
        self.assertEqual(stamps, sorted(stamps, reverse=True))

    def test_task_log_is_bounded_to_evidence(self) -> None:
        detail = dashboard.task_detail(self.root, "F-01")
        log = detail["gate_logs"][0]["log"].split("/")[-1]
        text = dashboard.task_log(self.root, "F-01", log)
        self.assertTrue(text)
        with self.assertRaises(PolierError):
            dashboard.task_log(self.root, "F-01", "../board.json")

    def test_file_preview_refuses_traversal(self) -> None:
        preview = dashboard.file_preview(self.root, "README.md")
        self.assertIn("text", preview)
        with self.assertRaises(PolierError):
            dashboard.file_preview(self.root, "../../etc/passwd")

    def test_repo_files_lists_project(self) -> None:
        entries = dashboard.repo_files(self.root)
        names = {entry["name"] for entry in entries}
        self.assertIn("board.json", names)
        self.assertIn("tasks", names)

    def test_git_common_dir_from_a_subdirectory(self) -> None:
        common = paths.git_common_dir(self.root / "docs")
        self.assertEqual(common.name, ".git")
        self.assertTrue((common / "HEAD").is_file())


if __name__ == "__main__":
    unittest.main()
