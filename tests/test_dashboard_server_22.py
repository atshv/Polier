"""Dashboard API 2.2: timeline, cycles, modules, coverage and analytics."""
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


class Dashboard22Test(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_project()
        self.app = DashboardApp(self.root, host="127.0.0.1", port=0, quiet=True)
        self.server = DashboardServer(self.app, port=0).start()
        self.base = f"http://127.0.0.1:{self.app.port}"

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_feature_defaults_are_on(self) -> None:
        status, settings = request(self.base, "/api/settings")
        self.assertEqual(status, 200)
        for feature in ("timeline", "cycles", "modules", "coverage", "analytics"):
            self.assertTrue(settings["features"][feature], feature)
        self.assertEqual(settings["project"]["defaults"]["hours_per_day"], 4)

    def test_timeline_endpoint(self) -> None:
        status, model = request(self.base, "/api/timeline")
        self.assertEqual(status, 200, model)
        self.assertIn("stages", model)
        self.assertIn("critical_path", model)
        self.assertIn("days", model)
        self.assertGreater(model["totals"]["tasks"], 0)

    def test_planning_endpoints(self) -> None:
        status, cycles = request(self.base, "/api/cycles")
        self.assertEqual(status, 200)
        self.assertIn("cycles", cycles)
        status, modules = request(self.base, "/api/modules")
        self.assertEqual(status, 200)
        self.assertIn("modules", modules)
        status, coverage = request(self.base, "/api/coverage")
        self.assertEqual(status, 200)
        self.assertIn("requirements", coverage)
        self.assertIn("summary", coverage)
        status, analytics = request(self.base, "/api/analytics")
        self.assertEqual(status, 200)
        self.assertIn("kpis", analytics)
        self.assertIn("throughput", analytics)

    def test_planning_dates_round_trip(self) -> None:
        status, task = request(self.base, "/api/plan/tasks/ENG-01", "PATCH",
                               {"planned_start": "2026-12-01", "target": "2026-12-10"}, ACTION)
        self.assertEqual(status, 200, task)
        board = json.loads((self.root / "board.json").read_text(encoding="utf-8"))
        self.assertEqual(board["schema_version"], "1.2")
        status, model = request(self.base, "/api/timeline")
        entry = next(task for lane in model["stages"] for task in lane["tasks"]
                     if task["id"] == "ENG-01")
        self.assertEqual(entry["start"], "2026-12-01")
        self.assertEqual(entry["end"], "2026-12-10")


if __name__ == "__main__":
    unittest.main()
