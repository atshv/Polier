"""Dashboard API 2.1: settings, labels, views, filters, worklog, me/inbox."""
from __future__ import annotations

import json
import unittest
import urllib.error
import urllib.request

from dash_helpers import sample_project

from server.app import DashboardApp, DashboardServer


def request(base: str, path: str, method: str = "GET", body=None, headers=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


ACTION = {"X-Polier-Action": "1"}


class Dashboard21Test(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_project()
        self.app = DashboardApp(self.root, host="127.0.0.1", port=0, quiet=True)
        self.server = DashboardServer(self.app, port=0).start()
        self.base = f"http://127.0.0.1:{self.app.port}"

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_settings(self) -> None:
        status, settings = request(self.base, "/api/settings")
        self.assertEqual(status, 200)
        self.assertEqual(settings["me"], "owner")
        self.assertTrue(settings["features"]["inbox"])
        self.assertTrue(settings["features"]["timeline"])
        self.assertTrue(settings["features"]["analytics"])
        status, updated = request(self.base, "/api/settings", "PUT",
                                  {"features": {"timeline": False}}, ACTION)
        self.assertEqual(status, 200, updated)
        self.assertFalse(updated["features"]["timeline"])
        status, settings = request(self.base, "/api/settings")
        self.assertFalse(settings["project"]["features"]["timeline"])
        self.assertTrue((self.root / "dashboard.json").is_file())

    def test_label_crud(self) -> None:
        status, created = request(self.base, "/api/settings/labels", "POST",
                                  {"id": "docs", "title": "Docs", "color": "blue",
                                   "group": "theme"}, ACTION)
        self.assertEqual(status, 200, created)
        status, updated = request(self.base, "/api/settings/labels/docs", "PUT",
                                  {"title": "Documentation"}, ACTION)
        self.assertEqual(status, 200)
        self.assertEqual(updated["label"]["title"], "Documentation")
        status, deleted = request(self.base, "/api/settings/labels/docs", "DELETE", {}, ACTION)
        self.assertEqual(status, 200)
        self.assertEqual(deleted["deleted"], "docs")

    def test_views(self) -> None:
        status, values = request(self.base, "/api/views")
        self.assertEqual(status, 200)
        self.assertIn("all", [view["id"] for view in values["builtin"]])
        status, saved = request(self.base, "/api/views/my-review", "PUT", {
            "name": "My review", "kind": "table",
            "filters": [{"field": "status", "op": "any_of", "value": ["review"]}],
            "group_by": "owner"}, ACTION)
        self.assertEqual(status, 200, saved)
        status, values = request(self.base, "/api/views")
        self.assertIn("my-review", [view["id"] for view in values["saved"]])
        status, _ = request(self.base, "/api/views/my-review", "DELETE", {}, ACTION)
        self.assertEqual(status, 200)

    def test_filter_metadata(self) -> None:
        status, meta = request(self.base, "/api/filters/fields")
        self.assertEqual(status, 200)
        self.assertIn("status", meta["fields"])
        self.assertIn("any_of", meta["operators"]["status"])
        self.assertIn("label", meta["group_by"])

    def test_worklog(self) -> None:
        status, report = request(self.base, "/api/worklog?task=F-01")
        self.assertEqual(status, 200)
        self.assertIn("totals", report)
        self.assertEqual(report["task"], "F-01")
        status, summary = request(self.base, "/api/worklog")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(summary["totals"]["tasks"], 1)

    def test_me_and_inbox(self) -> None:
        status, me = request(self.base, "/api/me")
        self.assertEqual(status, 200)
        self.assertEqual(me["me"], "owner")
        request(self.base, "/api/approvals/request", "POST",
                {"action": "new_dependency", "task": "ENG-01", "note": "x"}, ACTION)
        status, summary = request(self.base, "/api/inbox")
        self.assertEqual(status, 200)
        approval_items = [item for item in summary["items"] if item["kind"] == "approval"]
        self.assertTrue(approval_items)
        status, _ = request(self.base, "/api/inbox/read", "POST",
                            {"ids": [approval_items[0]["id"]]}, ACTION)
        self.assertEqual(status, 200)
        status, summary = request(self.base, "/api/inbox?unread=1")
        self.assertNotIn(approval_items[0]["id"], [item["id"] for item in summary["items"]])

    def test_estimate_can_be_cleared(self) -> None:
        status, task = request(self.base, "/api/plan/tasks", "POST", {
            "id": "DASH-03", "title": "Estimable task", "goal": "Do it.", "stage": "surface",
            "scope_write": ["docs/"], "acceptance": ["A1"], "gates": ["board-check"],
            "estimate_hours": 4}, ACTION)
        self.assertEqual(status, 200, task)
        status, updated = request(self.base, "/api/plan/tasks/DASH-03", "PATCH",
                                  {"estimate_hours": None}, ACTION)
        self.assertEqual(status, 200, updated)
        board = json.loads((self.root / "board.json").read_text(encoding="utf-8"))
        saved = next(entry for entry in board["tasks"] if entry["id"] == "DASH-03")
        self.assertNotIn("estimate_hours", saved)

    def test_inbox_mark_all(self) -> None:
        request(self.base, "/api/approvals/request", "POST",
                {"action": "new_dependency", "task": "ENG-01", "note": "x"}, ACTION)
        status, state = request(self.base, "/api/inbox/read", "POST", {"all": True}, ACTION)
        self.assertEqual(status, 200, state)
        self.assertGreaterEqual(len(state["read"]), 1)
        status, summary = request(self.base, "/api/inbox")
        self.assertEqual(summary["counts"]["unread"], 0)

    def test_invalid_session_settings_are_400(self) -> None:
        status, error = request(self.base, "/api/config", "PUT",
                                {"session": {"command": "not-a-list"}}, ACTION)
        self.assertEqual(status, 400, error)
        self.assertIn("command", error["error"])

    def test_plan_task_with_label_upgrades_board(self) -> None:
        request(self.base, "/api/settings/labels", "POST",
                {"id": "docs", "title": "Docs", "color": "blue", "group": "theme"}, ACTION)
        status, task = request(self.base, "/api/plan/tasks", "POST", {
            "id": "DASH-01", "title": "Docs task", "goal": "Write docs.", "stage": "surface",
            "scope_write": ["docs/"], "acceptance": ["A1"], "gates": ["board-check"],
            "labels": ["docs"], "estimate_hours": 3}, ACTION)
        self.assertEqual(status, 200, task)
        board = json.loads((self.root / "board.json").read_text(encoding="utf-8"))
        self.assertEqual(board["schema_version"], "1.1")
        saved = next(entry for entry in board["tasks"] if entry["id"] == "DASH-01")
        self.assertEqual(saved["labels"], ["docs"])
        status, _ = request(self.base, "/api/plan/tasks/DASH-01", "DELETE", {}, ACTION)
        self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main()
