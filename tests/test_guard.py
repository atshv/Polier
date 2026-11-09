"""core/guard.py and tools/guard.py: the one answer the DSH plugin shows for a write or a command."""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from core.guard import decide
from tests.helpers import make_project, run_tool, task

POLICY = Path(__file__).resolve().parents[1] / "templates" / "policy.json"


def request(root: Path, **fields) -> dict:
    data = {"root": str(root), "cwd": str(root), "role": "worker", "tasks": ["M01"]}
    data.update(fields)
    return data


class Writes(unittest.TestCase):
    def setUp(self):
        self.root = make_project([task("M01", scope_write=["src/app.py", "package.json"])])
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_scope(self):
        self.assertIsNone(decide(request(self.root, path="src/app.py"))["deny"])
        deny = decide(request(self.root, path="README.md"))["deny"]
        self.assertIn("outside the write scope of M01", deny)
        self.assertIn("Allowed: src/app.py, package.json", deny)
        self.assertIn("lead-owned", decide(request(self.root, path="board.json"))["deny"])

    def test_roles(self):
        self.assertIsNone(decide(request(self.root, role="lead", path="README.md"))["deny"])
        self.assertIsNone(decide(request(self.root, role="off", path="README.md"))["deny"])
        self.assertIsNone(decide(request(self.root, role="reviewer", path="reviews/M01.md"))["deny"])
        self.assertIn("writes only under reviews/",
                      decide(request(self.root, role="reviewer", path="src/app.py"))["deny"])

    def test_specialist_narrows_the_scope(self):
        role = {"title": "Frontend builder", "writes": ["src/ui"]}
        deny = decide(request(self.root, path="src/app.py", specialist=role))["deny"]
        self.assertIn("the role Frontend builder writes only src/ui", deny)
        self.assertIsNone(decide(request(self.root, path="reviews/evidence/a.log", specialist=role))["deny"])

    def test_policy_paths(self):
        shutil.copy(POLICY, self.root / "policy.json")
        (self.root / ".env").write_text("", encoding="utf-8")
        deny = decide(request(self.root, path=".env", tasks=[]))["deny"]
        self.assertIn("protected path", deny)
        deny = decide(request(self.root, path="package.json"))["deny"]
        self.assertIn("new_dependency", deny)
        self.assertIn("task M01", deny)
        self.assertIsNone(decide(request(self.root, role="lead", path="package.json"))["deny"])


class Commands(unittest.TestCase):
    def setUp(self):
        self.root = make_project([task("M01")])
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        shutil.copy(POLICY, self.root / "policy.json")

    def test_deny_and_lead_only(self):
        deny = decide(request(self.root, command="git push origin main"))["deny"]
        self.assertIn("blocked for every role, a lead included", deny)
        self.assertIn("deny", decide(request(self.root, role="lead", command="git push"))["deny"])
        worker = decide(request(self.root, command="python3 tools/state.py set M01 done"))["deny"]
        self.assertIn("only the lead may run", worker)
        self.assertIsNone(decide(request(self.root, role="lead",
                                         command="python3 tools/state.py set M01 done"))["deny"])

    def test_kills_are_flagged_not_denied(self):
        answer = decide(request(self.root, command="lsof -ti:3000 | xargs kill"))
        self.assertIsNone(answer["deny"])
        self.assertTrue(answer["kills"])
        self.assertFalse(decide(request(self.root, command="echo kill"))["kills"])


class Cli(unittest.TestCase):
    def test_json_in_json_out(self):
        root = make_project([task("M01")])
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        result = run_tool("guard.py", json.dumps(request(root, path="README.md")))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("blocked", json.loads(result.stdout)["deny"])
        self.assertEqual(run_tool("guard.py", "not json").returncode, 2)


if __name__ == "__main__":
    unittest.main()
