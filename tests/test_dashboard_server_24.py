"""Dashboard API 2.4: assistant, automations, GitHub and bulk operations."""
from __future__ import annotations

import json
import sys
import time
import unittest
import urllib.error
import urllib.request

from dash_helpers import sample_project

from core import runtime
from server.app import DashboardApp, DashboardServer

FAKE = '''\
import json
answer = """Stage 7 is blocked by the spike.

```json
{"proposals": [{"kind": "state", "title": "Block ENG-01", "reason": "needs the spike",
                "payload": {"task": "ENG-01", "status": "blocked", "note": "assistant"}}]}
```"""
print(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                  "usage": {"input_tokens": 10, "output_tokens": 5},
                  "result": answer}), flush=True)
'''


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
RULES = {"version": 1, "rules": [
    {"id": "ready", "name": "Ready tasks", "enabled": True,
     "when": {"kind": "task_ready"}, "actions": [{"type": "open"}]}]}


class Dashboard24Test(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_project()
        fake = self.root / "fake_assistant.py"
        fake.write_text(FAKE, encoding="utf-8")
        runtime.write_json(runtime.runtime_dir(self.root) / "config.json",
                           {"session": {"provider": "custom",
                                        "command": [sys.executable, str(fake)],
                                        "permission_mode": None,
                                        "allowed_tools": [],
                                        "timeout_s": 60}})
        self.app = DashboardApp(self.root, host="127.0.0.1", port=0, quiet=True)
        self.server = DashboardServer(self.app, port=0).start()
        self.base = f"http://127.0.0.1:{self.app.port}"

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_feature_defaults(self) -> None:
        status, settings = request(self.base, "/api/settings")
        self.assertEqual(status, 200)
        for feature in ("assistant", "automations", "github"):
            self.assertTrue(settings["features"][feature], feature)

    def test_automations_file_and_run(self) -> None:
        status, saved = request(self.base, "/api/automations", "PUT", RULES, ACTION)
        self.assertEqual(status, 200, saved)
        status, loaded = request(self.base, "/api/automations")
        self.assertEqual(status, 200)
        self.assertEqual(loaded["errors"], [])
        self.assertEqual(len(loaded["automations"]["rules"]), 1)
        status, run = request(self.base, "/api/automations/run", "POST", {}, ACTION)
        self.assertEqual(status, 200, run)
        self.assertTrue(run["dry_run"])
        self.assertIn("matches", run)
        status, error = request(self.base, "/api/automations", "PUT",
                                {"version": 1, "rules": [{"id": "Bad"}]}, ACTION)
        self.assertEqual(status, 400)

    def test_github_unavailable_without_remote(self) -> None:
        status, value = request(self.base, "/api/github")
        self.assertEqual(status, 200)
        self.assertFalse(value["available"])
        self.assertIn("reason", value)

    def test_bulk_operations(self) -> None:
        status, result = request(self.base, "/api/bulk", "POST",
                                 {"action": "state", "tasks": ["ENG-01", "ENG-02"],
                                  "status": "blocked", "note": "bulk triage"}, ACTION)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["ok_count"], 2)
        self.assertEqual(result["failed_count"], 0)
        board = json.loads((self.root / "board.json").read_text(encoding="utf-8"))
        statuses = {task["id"]: task["status"] for task in board["tasks"]}
        self.assertEqual(statuses["ENG-01"], "blocked")
        self.assertEqual(statuses["ENG-02"], "blocked")
        status, claimed = request(self.base, "/api/bulk", "POST",
                                  {"action": "claim", "tasks": ["API-01"]}, ACTION)
        self.assertEqual(claimed["ok_count"], 1, claimed)
        status, released = request(self.base, "/api/bulk", "POST",
                                   {"action": "release", "tasks": ["API-01"]}, ACTION)
        self.assertEqual(released["ok_count"], 1)
        status, labels = request(self.base, "/api/bulk", "POST",
                                 {"action": "labels", "tasks": ["ENG-02"],
                                  "labels": ["bug"]}, ACTION)
        self.assertEqual(labels["ok_count"], 1)
        status, failure = request(self.base, "/api/bulk", "POST",
                                  {"action": "state", "tasks": ["ENG-02"],
                                   "status": "done"}, ACTION)
        self.assertEqual(failure["failed_count"], 1)
        status, error = request(self.base, "/api/bulk", "POST",
                                {"action": "nope", "tasks": ["ENG-01"]}, ACTION)
        self.assertEqual(status, 200)
        self.assertEqual(error["failed_count"], 1)

    def test_assistant_chat_and_apply(self) -> None:
        status, conversation = request(self.base, "/api/assistant/chat", "POST",
                                       {"message": "What is blocking the engine?"}, ACTION)
        self.assertEqual(status, 200, conversation)
        conversation_id = conversation["id"]
        deadline = time.time() + 30
        current = None
        while time.time() < deadline:
            status, current = request(self.base, f"/api/assistant/{conversation_id}")
            if current and not current.get("pending"):
                break
            time.sleep(0.1)
        self.assertIsNotNone(current)
        self.assertFalse(current.get("pending"), current)
        assistant_messages = [message for message in current["messages"]
                              if message.get("role") == "assistant"]
        self.assertTrue(assistant_messages)
        self.assertIn("Stage 7 is blocked", assistant_messages[-1]["content"])
        proposals = assistant_messages[-1].get("proposals") or []
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["kind"], "state")
        status, applied = request(self.base, "/api/assistant/apply", "POST",
                                  {"conversation_id": conversation_id, "proposal": proposals[0]},
                                  ACTION)
        self.assertEqual(status, 200, applied)
        board = json.loads((self.root / "board.json").read_text(encoding="utf-8"))
        task = next(entry for entry in board["tasks"] if entry["id"] == "ENG-01")
        self.assertEqual(task["status"], "blocked")
        status, current = request(self.base, f"/api/assistant/{conversation_id}")
        self.assertTrue(any("Applied proposal" in message.get("content", "")
                            for message in current["messages"]))

    def test_read_only_refuses_assistant_and_bulk(self) -> None:
        app = DashboardApp(self.root, host="127.0.0.1", port=0, quiet=True, read_only=True)
        server = DashboardServer(app, port=0).start()
        base = f"http://127.0.0.1:{app.port}"
        try:
            status, _ = request(base, "/api/assistant/chat", "POST",
                                {"message": "hi"}, ACTION)
            self.assertEqual(status, 403)
            status, _ = request(base, "/api/bulk", "POST",
                                {"action": "claim", "tasks": ["ENG-01"]}, ACTION)
            self.assertEqual(status, 403)
            status, run = request(base, "/api/automations/run", "POST", {})
            self.assertEqual(status, 200, run)
            self.assertTrue(run["dry_run"])
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
