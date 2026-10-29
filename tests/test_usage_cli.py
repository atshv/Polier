"""tools/usage.py: record token use and show it against the budget."""
from __future__ import annotations

import json
import unittest

from helpers import make_project, run_tool, task


def with_budget(root, tokens):
    (root / "policy.json").write_text(json.dumps(
        {"version": 1, "budget": {"max_tokens_per_task": tokens, "warn_at": 0.5}}))


class UsageCli(unittest.TestCase):
    def test_record_and_show(self):
        root = make_project([task("M01", status="in_progress"), task("M02", status="pending")])
        with_budget(root, 10_000)
        first = run_tool("usage.py", "--root", str(root), "record", "M01", "--tokens", "6000", "--session", "a")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("WARN: 6,000 of 10,000", first.stdout)
        over = run_tool("usage.py", "--root", str(root), "record", "M01", "--tokens", "5000")
        self.assertEqual(over.returncode, 1)
        self.assertIn("OVER", over.stdout)
        shown = run_tool("usage.py", "--root", str(root), "show", "--json")
        data = json.loads(shown.stdout)
        self.assertEqual(shown.returncode, 1)
        self.assertEqual(data["tasks"], [{"task": "M01", "tokens": 11_000, "sessions": 2, "state": "over"}])
        text = run_tool("usage.py", "--root", str(root), "show")
        self.assertIn("M01: 11,000 (110 %)  OVER", text.stdout)

    def test_without_budget_information_only(self):
        root = make_project([task("M01", status="in_progress")])
        run_tool("usage.py", "--root", str(root), "record", "M01", "--tokens", "999999")
        shown = run_tool("usage.py", "--root", str(root), "show")
        self.assertEqual(shown.returncode, 0)
        self.assertIn("budget: none", shown.stdout)

    def test_unknown_task(self):
        root = make_project([task("M01")])
        result = run_tool("usage.py", "--root", str(root), "record", "X99", "--tokens", "5")
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
