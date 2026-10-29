"""The greenfield plan flow over the HTTP API, with a fake generator provider."""
from __future__ import annotations

import json
import sys
import time
import unittest
import urllib.error
import urllib.request

from dash_helpers import empty_project

from core import runtime
from server.app import DashboardApp, DashboardServer

FAKE = """\
import json
print(json.dumps({"type": "system", "subtype": "init", "model": "fake"}), flush=True)
print(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                  "usage": {"input_tokens": 10, "output_tokens": 5},
                  "result": "planned"}), flush=True)
"""


def call(base, path, method="GET", body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


class PlanFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = empty_project()
        fake = self.root / "fake_generator.py"
        fake.write_text(FAKE, encoding="utf-8")
        config = runtime.runtime_dir(self.root) / "config.json"
        runtime.write_json(config, {"session": {"provider": "custom",
                                                "command": [sys.executable, str(fake)],
                                                "timeout_s": 30}})
        self.app = DashboardApp(self.root, host="127.0.0.1", port=0, quiet=True)
        self.server = DashboardServer(self.app, port=0).start()
        self.base = f"http://127.0.0.1:{self.app.port}"

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_wizard_starts_a_generator_session_and_approve_needs_a_board(self) -> None:
        status, snapshot = call(self.base, "/api/snapshot")
        self.assertEqual(status, 409)
        status, plan = call(self.base, "/api/plan")
        self.assertEqual(status, 200)
        self.assertFalse(plan["board_present"])
        status, result = call(self.base, "/api/plan/generator", "POST", {"answers": {
            "mode": "greenfield", "name": "Notes", "goal": "A calm note-taking app."}},
            {"X-Polier-Action": "1"})
        self.assertEqual(status, 200, result)
        session = result["session"]
        self.assertEqual(session["role"], "generator")
        deadline = time.time() + 20
        while time.time() < deadline:
            status, current = call(self.base, "/api/sessions/" + session["id"])
            if current["status"] not in ("starting", "running"):
                break
            time.sleep(0.05)
        self.assertEqual(current["status"], "done", current)
        self.assertEqual(current["tokens"], 15)
        status, error = call(self.base, "/api/plan/approve", "POST", {},
                             {"X-Polier-Action": "1"})
        self.assertEqual(status, 400)
        self.assertIn("board.json", error["error"])


if __name__ == "__main__":
    unittest.main()
