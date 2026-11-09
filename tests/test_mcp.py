"""tools/mcp.py: the slim MCP server over stdio."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest

from helpers import PACKAGE, TOOLS, make_project, task

sys.path.insert(0, str(PACKAGE))

from core import factory  # noqa: E402


def session(root, *messages, read_only=False):
    argv = [sys.executable, str(TOOLS / "mcp.py"), "--root", str(root)]
    if read_only:
        argv.append("--read-only")
    text = "\n".join(json.dumps(m) for m in messages) + "\n"
    result = subprocess.run(argv, input=text, capture_output=True, text=True, check=True)
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def call(root, name, arguments=None, read_only=False):
    out = session(root, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                         "params": {"name": name, "arguments": arguments or {}}}, read_only=read_only)
    return out[0]["result"]


class Mcp(unittest.TestCase):
    def setUp(self):
        self.root = make_project([task("M01", status="pending")])
        factory.init(self.root, ["web"], [])

    def test_handshake_and_tool_list(self):
        out = session(self.root,
                      {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                      {"jsonrpc": "2.0", "method": "notifications/initialized"},
                      {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(out[0]["result"]["serverInfo"]["name"], "polier")
        self.assertEqual(out[0]["result"]["serverInfo"]["version"],
                         (PACKAGE / "VERSION").read_text().strip())
        names = {tool["name"] for tool in out[1]["result"]["tools"]}
        self.assertIn("polier_factory", names)
        self.assertIn("polier_gate", names)

    def test_factory_tools(self):
        result = call(self.root, "polier_factory")
        self.assertFalse(result["isError"], result)
        value = json.loads(result["content"][0]["text"])
        self.assertEqual(value["current"], "idea")
        result = call(self.root, "polier_factory_item", {"item": "rel-web-01"})
        self.assertTrue(json.loads(result["content"][0]["text"])["applies"])
        result = call(self.root, "polier_factory_set", {"item": "IDEA-06", "status": "na", "reason": "hobby"})
        self.assertFalse(result["isError"], result)
        self.assertEqual(factory.load(self.root)["items"]["IDEA-06"]["status"], "na")

    def test_read_only_refuses_writes(self):
        result = call(self.root, "polier_factory_set", {"item": "IDEA-06", "status": "na", "reason": "x"},
                      read_only=True)
        self.assertTrue(result["isError"])
        self.assertIn("read-only", result["content"][0]["text"])

    def test_task_tools(self):
        value = json.loads(call(self.root, "polier_tasks")["content"][0]["text"])
        self.assertEqual(value[0]["id"], "M01")
        result = call(self.root, "polier_dispatch")
        self.assertFalse(result["isError"], result)
        result = call(self.root, "polier_task", {"task": "M01"})
        self.assertFalse(result["isError"], result)


if __name__ == "__main__":
    unittest.main()
