"""tools/assistant.py, tools/automations.py and tools/github.py (2.4 CLI)."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest

from dash_helpers import PACKAGE, sample_project

FAKE = '''\
import json
print(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                  "usage": {"input_tokens": 5, "output_tokens": 5},
                  "result": "Nothing is blocked right now."}), flush=True)
'''


def run_tool(name, *args, timeout=90):
    return subprocess.run([sys.executable, str(PACKAGE / "tools" / name), *args],
                          capture_output=True, text=True, timeout=timeout)


class AssistantCliTest(unittest.TestCase):
    def test_ask_and_list(self) -> None:
        root = sample_project()
        fake = root / "fake_cli_assistant.py"
        fake.write_text(FAKE, encoding="utf-8")
        from core import runtime
        runtime.write_json(runtime.runtime_dir(root) / "config.json",
                           {"session": {"provider": "custom",
                                        "command": [sys.executable, str(fake)],
                                        "permission_mode": None, "allowed_tools": []}})
        result = run_tool("assistant.py", "ask", "What is blocked?", "--root", str(root), "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        answers = [message for message in value["messages"] if message.get("role") == "assistant"]
        self.assertTrue(answers)
        self.assertIn("Nothing is blocked", answers[-1]["content"])
        listing = run_tool("assistant.py", "list", "--root", str(root), "--json")
        self.assertEqual(listing.returncode, 0)
        self.assertEqual(len(json.loads(listing.stdout)["conversations"]), 1)


class AutomationsCliTest(unittest.TestCase):
    def test_init_validate_run(self) -> None:
        root = sample_project()
        self.assertEqual(run_tool("automations.py", "init", "--root", str(root)).returncode, 0)
        self.assertEqual(run_tool("automations.py", "validate", "--root", str(root)).returncode, 0)
        result = run_tool("automations.py", "run", "--json", "--root", str(root))
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertTrue(value["dry_run"])
        self.assertIn("matches", value)
        listing = run_tool("automations.py", "list", "--json", "--root", str(root))
        self.assertEqual(listing.returncode, 0)


class GithubCliTest(unittest.TestCase):
    def test_status_is_graceful(self) -> None:
        root = sample_project()
        result = run_tool("github.py", "status", "--json", "--root", str(root))
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertIn("available", value)


if __name__ == "__main__":
    unittest.main()
