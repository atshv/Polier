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
        for name in ("polier_settings", "polier_views", "polier_worklog",
                     "polier_me", "polier_inbox", "polier_inbox_read",
                     "polier_timeline", "polier_cycles", "polier_modules",
                     "polier_coverage", "polier_analytics",
                     "polier_pages", "polier_page", "polier_pages_search",
                     "polier_intake", "polier_intake_add", "polier_templates"):
            self.assertIn(name, tools)
        snapshot = json.loads(by_id[3]["result"]["content"][0]["text"])
        self.assertEqual(snapshot["project"]["name"], "canvas-mini")
        self.assertEqual(len(snapshot["tasks"]), 8)
        detail = json.loads(by_id[4]["result"]["content"][0]["text"])
        self.assertEqual(detail["task"]["id"], "F-01")

    def test_cockpit_tools(self) -> None:
        root = sample_project()
        process, responses = mcp_session(root, [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "polier_settings", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "polier_views", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "polier_worklog", "arguments": {"task": "F-01"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "polier_me", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
             "params": {"name": "polier_inbox", "arguments": {}}},
        ])
        self.assertEqual(process.returncode, 0, process.stderr)
        by_id = {response.get("id"): response for response in responses}
        settings = json.loads(by_id[1]["result"]["content"][0]["text"])
        self.assertIn("features", settings)
        self.assertIn("labels", settings)
        views = json.loads(by_id[2]["result"]["content"][0]["text"])
        self.assertIn("all", [view["id"] for view in views["builtin"]])
        worklog = json.loads(by_id[3]["result"]["content"][0]["text"])
        self.assertEqual(worklog["task"], "F-01")
        me = json.loads(by_id[4]["result"]["content"][0]["text"])
        self.assertEqual(me["me"], "owner")
        inbox = json.loads(by_id[5]["result"]["content"][0]["text"])
        self.assertIn("items", inbox)
        self.assertIn("counts", inbox)

    def test_planning_tools(self) -> None:
        root = sample_project()
        calls = [
            ("polier_timeline", {}),
            ("polier_cycles", {}),
            ("polier_modules", {}),
            ("polier_coverage", {}),
            ("polier_analytics", {}),
        ]
        messages = [{"jsonrpc": "2.0", "id": index + 1, "method": "tools/call",
                     "params": {"name": name, "arguments": arguments}}
                    for index, (name, arguments) in enumerate(calls)]
        process, responses = mcp_session(root, messages)
        self.assertEqual(process.returncode, 0, process.stderr)
        by_id = {response.get("id"): response for response in responses}
        timeline = json.loads(by_id[1]["result"]["content"][0]["text"])
        self.assertIn("critical_path", timeline)
        cycles = json.loads(by_id[2]["result"]["content"][0]["text"])
        self.assertIn("cycles", cycles)
        modules = json.loads(by_id[3]["result"]["content"][0]["text"])
        self.assertIn("modules", modules)
        coverage = json.loads(by_id[4]["result"]["content"][0]["text"])
        self.assertIn("summary", coverage)
        analytics = json.loads(by_id[5]["result"]["content"][0]["text"])
        self.assertIn("kpis", analytics)

    def test_knowledge_tools(self) -> None:
        root = sample_project()
        process, responses = mcp_session(root, [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "polier_pages", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "polier_page", "arguments": {"path": "README.md"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "polier_pages_search", "arguments": {"q": "contract"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "polier_intake", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
             "params": {"name": "polier_templates", "arguments": {}}},
        ])
        self.assertEqual(process.returncode, 0, process.stderr)
        by_id = {response.get("id"): response for response in responses}
        pages = json.loads(by_id[1]["result"]["content"][0]["text"])
        self.assertGreater(pages["counts"]["pages"], 2)
        page = json.loads(by_id[2]["result"]["content"][0]["text"])
        self.assertTrue(page["text"])
        search = json.loads(by_id[3]["result"]["content"][0]["text"])
        self.assertIn("results", search)
        entry = json.loads(by_id[4]["result"]["content"][0]["text"])
        self.assertIn("entries", entry)
        templates = json.loads(by_id[5]["result"]["content"][0]["text"])
        self.assertIn("templates", templates)

    def test_read_only_refuses_writes(self) -> None:
        root = sample_project()
        process, responses = mcp_session(root, [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "polier_state_set",
                        "arguments": {"task": "ENG-01", "status": "blocked", "note": "x"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "polier_unknown", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "polier_inbox_read", "arguments": {"all": True}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "polier_intake_add", "arguments": {"title": "Read-only"}}},
        ], extra=["--read-only"])
        self.assertEqual(process.returncode, 0)
        by_id = {response.get("id"): response for response in responses}
        self.assertTrue(by_id[1]["result"]["isError"])
        self.assertIn("read-only", by_id[1]["result"]["content"][0]["text"])
        self.assertTrue(by_id[2]["result"]["isError"])
        self.assertTrue(by_id[3]["result"]["isError"])
        self.assertIn("read-only", by_id[3]["result"]["content"][0]["text"])
        self.assertTrue(by_id[4]["result"]["isError"])


if __name__ == "__main__":
    unittest.main()
