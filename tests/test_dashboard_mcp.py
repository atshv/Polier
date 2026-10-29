"""tools/mcp.py: the MCP stdio server."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest

from dash_helpers import PACKAGE, sample_project


def mcp_session(root, messages, extra=None):
    argv = [sys.executable, str(PACKAGE / "tools" / "mcp.py"), "--root", str(root)]
    if extra:
        argv += extra
    process = subprocess.run(argv, input="\n".join(json.dumps(message) for message in messages) + "\n",
                             capture_output=True, text=True, timeout=60)
    responses = []
    for line in process.stdout.splitlines():
        line = line.strip()
        if line:
            responses.append(json.loads(line))
    return process, responses


class McpTest(unittest.TestCase):
    def test_initialize_list_and_snapshot(self) -> None:
        root = sample_project()
        process, responses = mcp_session(root, [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "polier_snapshot", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "polier_task", "arguments": {"task": "F-01"}}},
        ])
        self.assertEqual(process.returncode, 0, process.stderr)
        by_id = {response.get("id"): response for response in responses}
        self.assertEqual(by_id[1]["result"]["serverInfo"]["name"], "polier")
        tools = {tool["name"] for tool in by_id[2]["result"]["tools"]}
        self.assertIn("polier_snapshot", tools)
        self.assertIn("polier_state_set", tools)
        snapshot = json.loads(by_id[3]["result"]["content"][0]["text"])
        self.assertEqual(snapshot["project"]["name"], "canvas-mini")
        self.assertEqual(len(snapshot["tasks"]), 8)
        detail = json.loads(by_id[4]["result"]["content"][0]["text"])
        self.assertEqual(detail["task"]["id"], "F-01")

    def test_read_only_refuses_writes(self) -> None:
        root = sample_project()
        process, responses = mcp_session(root, [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "polier_state_set",
                        "arguments": {"task": "ENG-01", "status": "blocked", "note": "x"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "polier_unknown", "arguments": {}}},
        ], extra=["--read-only"])
        self.assertEqual(process.returncode, 0)
        by_id = {response.get("id"): response for response in responses}
        self.assertTrue(by_id[1]["result"]["isError"])
        self.assertIn("read-only", by_id[1]["result"]["content"][0]["text"])
        self.assertTrue(by_id[2]["result"]["isError"])


if __name__ == "__main__":
    unittest.main()
