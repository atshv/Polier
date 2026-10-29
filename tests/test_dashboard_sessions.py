"""server/sessions.py: headless session lifecycle with a fake provider."""
from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path

from dash_helpers import PACKAGE, empty_project, sample_project

from core import claims, runs
from core.errors import PolierError
from server.sessions import SessionManager

FAKE = '''\
import json, sys, time
for line in [
    {"type": "system", "subtype": "init", "model": "fake"},
    {"type": "assistant", "message": {"content": [{"type": "text", "text": "working on it"}]}},
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read",
                                                  "input": {"file_path": "board.json"}}]}},
    {"type": "result", "subtype": "success", "is_error": False,
     "usage": {"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 5},
     "result": "done"},
]:
    print(json.dumps(line), flush=True)
'''

SLOW = '''\
import json, sys, time
print(json.dumps({"type": "system", "subtype": "init", "model": "fake"}), flush=True)
time.sleep(30)
'''


def wait(manager: SessionManager, session_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        view = manager.get(session_id)
        if view["status"] not in ("starting", "running"):
            return view
        time.sleep(0.05)
    raise AssertionError(f"session {session_id} did not finish")


class SessionManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_project()
        self.fake = self.root / "fake_claude.py"
        self.fake.write_text(FAKE, encoding="utf-8")

    def _manager(self, script: Path, **extra) -> SessionManager:
        config = {"command": [sys.executable, str(script)], "permission_mode": None,
                  "allowed_tools": [], "timeout_s": 30, "max_concurrent": 2, **extra}
        return SessionManager(self.root, bus=None, config=config, package_root=PACKAGE)

    def test_session_runs_and_records_usage(self) -> None:
        manager = self._manager(self.fake)
        session = manager.start(task="F-01", role="worker")
        done = wait(manager, session["id"])
        self.assertEqual(done["status"], "done", done)
        self.assertEqual(done["exit_code"], 0)
        self.assertEqual(done["tokens"], 125)
        log = manager.log(session["id"])["text"]
        self.assertIn("working on it", log)
        self.assertIn("tool] Read", log)
        self.assertIn("done", log)
        self.assertEqual(runs.usage_total(self.root, "F-01"), 125)
        self.assertFalse(claims.live_claims(self.root))
        prompt = (Path(done["folder"]) / "prompt.md").read_text(encoding="utf-8")
        self.assertIn("Task F-01", prompt)
        self.assertIn("Scope (write only", prompt)

    def test_session_can_be_stopped(self) -> None:
        slow = self.root / "slow_claude.py"
        slow.write_text(SLOW, encoding="utf-8")
        manager = self._manager(slow)
        session = manager.start(task="ENG-01", role="worker")
        deadline = time.time() + 20
        while time.time() < deadline and manager.get(session["id"])["status"] != "running":
            time.sleep(0.05)
        manager.stop(session["id"])
        done = wait(manager, session["id"], timeout=20)
        self.assertEqual(done["status"], "stopped")
        self.assertFalse(claims.live_claims(self.root))

    def test_generator_session_works_before_the_board_exists(self) -> None:
        root = empty_project()
        fake = root / "fake_generator.py"
        fake.write_text(FAKE, encoding="utf-8")
        manager = SessionManager(root, bus=None, package_root=PACKAGE, config={
            "provider": "custom", "command": [sys.executable, str(fake)],
            "permission_mode": None, "allowed_tools": [], "timeout_s": 30})
        session = manager.start(role="generator", prompt="Plan this project.")
        done = wait(manager, session["id"])
        self.assertEqual(done["status"], "done")
        self.assertEqual(done["role"], "generator")
        self.assertEqual(done["tokens"], 125)
        with self.assertRaises(PolierError):
            manager.start(role="worker", task="M01")

    def test_only_one_session_per_task(self) -> None:
        manager = self._manager(self.fake, max_concurrent=2)
        first = manager.start(task="F-01", role="worker")
        try:
            with self.assertRaises(Exception):
                manager.start(task="F-01", role="reviewer")
        finally:
            manager.stop(first["id"])
            wait(manager, first["id"], timeout=20)


if __name__ == "__main__":
    unittest.main()
