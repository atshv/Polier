"""server/app.py: the local HTTP API (read endpoints, auth, actions, SSE)."""
from __future__ import annotations

import json
import unittest
import urllib.error
import urllib.request

from dash_helpers import sample_project

from server.app import ASSETS, DashboardApp, DashboardServer


def request(base: str, path: str, method: str = "GET", body=None, headers=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


class DashboardServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_project()
        self.app = DashboardApp(self.root, host="127.0.0.1", port=0, quiet=True)
        self.server = DashboardServer(self.app, port=0).start()
        self.base = f"http://127.0.0.1:{self.app.port}"

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_read_endpoints(self) -> None:
        status, health = request(self.base, "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(health["ok"])
        status, snapshot = request(self.base, "/api/snapshot")
        self.assertEqual(status, 200)
        self.assertEqual(snapshot["project"]["name"], "canvas-mini")
        self.assertEqual(len(snapshot["tasks"]), 8)
        status, detail = request(self.base, "/api/tasks/F-01")
        self.assertEqual(status, 200)
        self.assertTrue(detail["brief"]["text"])
        status, _ = request(self.base, "/api/tasks/NOPE-01")
        self.assertEqual(status, 404)
        status, plan = request(self.base, "/api/plan")
        self.assertEqual(status, 200)
        self.assertIn("fields", plan)

    def test_action_needs_header_and_csrf_origin(self) -> None:
        status, error = request(self.base, "/api/tasks/ENG-01/state", "POST",
                                {"status": "blocked", "note": "waiting"})
        self.assertEqual(status, 403)
        self.assertIn("X-Polier-Action", error["error"])
        status, error = request(self.base, "/api/tasks/ENG-01/state", "POST",
                                {"status": "blocked", "note": "waiting"},
                                {"X-Polier-Action": "1", "Origin": "http://evil.example"})
        self.assertEqual(status, 403)
        self.assertIn("cross-origin", error["error"])

    def test_state_action_updates_the_board(self) -> None:
        status, result = request(self.base, "/api/tasks/ENG-01/state", "POST",
                                 {"status": "blocked", "note": "needs the engine spike"},
                                 {"X-Polier-Action": "1"})
        self.assertEqual(status, 200, result)
        board = json.loads((self.root / "board.json").read_text(encoding="utf-8"))
        task = next(entry for entry in board["tasks"] if entry["id"] == "ENG-01")
        self.assertEqual(task["status"], "blocked")
        self.assertTrue((self.root / "runs" / "ENG-01.json").is_file())

    def test_read_only_refuses_actions(self) -> None:
        app = DashboardApp(self.root, host="127.0.0.1", port=0, quiet=True, read_only=True)
        server = DashboardServer(app, port=0).start()
        base = f"http://127.0.0.1:{app.port}"
        try:
            status, error = request(base, "/api/tasks/ENG-01/state", "POST",
                                    {"status": "blocked", "note": "x"}, {"X-Polier-Action": "1"})
            self.assertEqual(status, 403)
            self.assertIn("read-only", error["error"])
        finally:
            server.shutdown()

    def test_token_auth(self) -> None:
        app = DashboardApp(self.root, host="127.0.0.1", port=0, quiet=True, token="s3cret")
        server = DashboardServer(app, port=0).start()
        base = f"http://127.0.0.1:{app.port}"
        try:
            status, _ = request(base, "/api/health")
            self.assertEqual(status, 401)
            status, _ = request(base, "/api/health", headers={"Authorization": "Bearer s3cret"})
            self.assertEqual(status, 200)
        finally:
            server.shutdown()

    def test_event_stream_starts_with_ready(self) -> None:
        with urllib.request.urlopen(self.base + "/api/events", timeout=10) as response:
            self.assertEqual(response.status, 200)
            first = response.readline().decode("utf-8", errors="replace")
        self.assertIn("event: ready", first)

    def test_plan_validation_answers_with_400(self) -> None:
        status, error = request(self.base, "/api/plan/answers", "PUT",
                                {"answers": {"mode": "greenfield", "name": "x"}},
                                {"X-Polier-Action": "1"})
        self.assertEqual(status, 400, error)
        self.assertIn("goal", error["error"])

    def test_static_ui_is_served(self) -> None:
        if not (ASSETS / "index.html").is_file():
            self.skipTest("dashboard UI assets not built yet")
        with urllib.request.urlopen(self.base + "/", timeout=10) as response:
            html = response.read().decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("<html", html.lower())
        self.assertIn("/assets/app.js", html)


if __name__ == "__main__":
    unittest.main()
