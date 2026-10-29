"""Dashboard API 2.3: pages, intake and task templates."""
from __future__ import annotations

import json
import unittest
import urllib.error
import urllib.request

from dash_helpers import sample_project

from server.app import DashboardApp, DashboardServer


def request(base, path, method="GET", body=None, headers=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


ACTION = {"X-Polier-Action": "1"}


class Dashboard23Test(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_project()
        self.app = DashboardApp(self.root, host="127.0.0.1", port=0, quiet=True)
        self.server = DashboardServer(self.app, port=0).start()
        self.base = f"http://127.0.0.1:{self.app.port}"

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_feature_defaults_include_pages_and_intake(self) -> None:
        status, settings = request(self.base, "/api/settings")
        self.assertEqual(status, 200)
        self.assertTrue(settings["features"]["pages"])
        self.assertTrue(settings["features"]["intake"])
        self.assertTrue(settings["features"]["assistant"])

    def test_pages_endpoints(self) -> None:
        status, value = request(self.base, "/api/pages")
        self.assertEqual(status, 200)
        self.assertGreater(value["counts"]["pages"], 5)
        path = value["pages"][0]["path"]
        status, detail = request(self.base, "/api/page?path=" + path.replace("/", "%2F"))
        self.assertEqual(status, 200, detail)
        self.assertIn("text", detail)
        self.assertIn("history", detail)
        status, result = request(self.base, "/api/pages/search?q=contract")
        self.assertEqual(status, 200)
        self.assertIn("results", result)
        status, error = request(self.base, "/api/page?path=..%2Fboard.json")
        self.assertEqual(status, 404)
        status, favorites = request(self.base, "/api/pages/favorites", "PUT",
                                    {"favorites": [path]}, ACTION)
        self.assertEqual(status, 200)
        self.assertEqual(favorites["favorites"], [path])
        status, loaded = request(self.base, "/api/pages/favorites")
        self.assertEqual(loaded["favorites"], [path])

    def test_intake_lifecycle(self) -> None:
        status, entry = request(self.base, "/api/intake", "POST",
                                {"title": "Add a wiki", "description": "Browse docs",
                                 "kind": "idea", "priority": "high"}, ACTION)
        self.assertEqual(status, 200, entry)
        self.assertEqual(entry["id"], "IN-001")
        status, listing = request(self.base, "/api/intake")
        self.assertEqual(status, 200)
        self.assertEqual(listing["counts"]["proposed"], 1)
        status, updated = request(self.base, f"/api/intake/{entry['id']}", "PATCH",
                                  {"title": "Add a wiki page"}, ACTION)
        self.assertEqual(status, 200)
        self.assertEqual(updated["title"], "Add a wiki page")
        status, error = request(self.base, f"/api/intake/{entry['id']}/accept", "POST", {}, ACTION)
        self.assertEqual(status, 400, error)
        status, loaded = request(self.base, f"/api/intake/{entry['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(loaded["id"], entry["id"])
        self.assertIn("needs", error["error"])
        status, template = request(self.base, "/api/task-templates", "POST",
                                   {"id": "feature", "name": "Feature",
                                    "scope_write": ["docs/"], "acceptance": ["A1"],
                                    "gates": ["board-check"], "complexity": 3,
                                    "labels": ["feature"]}, ACTION)
        self.assertEqual(status, 200, template)
        status, result = request(self.base, f"/api/intake/{entry['id']}/accept", "POST",
                                 {"stage": "surface", "template": "feature",
                                  "note": "go"}, ACTION)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["intake"]["status"], "accepted")
        board = json.loads((self.root / "board.json").read_text(encoding="utf-8"))
        task = next(item for item in board["tasks"] if item["id"] == result["task"]["id"])
        self.assertEqual(task["title"], "Add a wiki page")
        self.assertEqual(task["labels"], ["feature"])
        status, second = request(self.base, "/api/intake", "POST",
                                 {"title": "Reject me"}, ACTION)
        status, rejected = request(self.base, f"/api/intake/{second['id']}/reject", "POST",
                                   {"note": "not now"}, ACTION)
        self.assertEqual(status, 200)
        self.assertEqual(rejected["status"], "rejected")

    def test_templates_and_template_plan_task(self) -> None:
        status, template = request(self.base, "/api/task-templates", "POST",
                                   {"from_task": "F-01", "id": "from-f01",
                                    "name": "From F-01"}, ACTION)
        self.assertEqual(status, 200, template)
        self.assertEqual(template["id"], "from-f01")
        status, listing = request(self.base, "/api/task-templates")
        self.assertEqual(status, 200)
        self.assertIn("from-f01", [item["id"] for item in listing["templates"]])
        status, task = request(self.base, "/api/plan/tasks", "POST",
                               {"id": "DASH-23", "title": "From template", "goal": "Do it.",
                                "stage": "surface", "template": "from-f01"}, ACTION)
        self.assertEqual(status, 200, task)
        self.assertEqual(task["gates"], ["layout"])
        status, deleted = request(self.base, "/api/task-templates/from-f01", "DELETE", {}, ACTION)
        self.assertEqual(status, 200)
        self.assertEqual(deleted["deleted"], True)

    def test_mutations_need_the_header(self) -> None:
        status, error = request(self.base, "/api/intake", "POST", {"title": "No header"})
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
