"""Token budget: policy section, usage store, checkpoint and dispatch."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core import policy, runs, state

from .fixtures import project, task, write_policy




def budget_project(tokens=10_000, warn=0.8, tasks=None):
    root = project(tasks or [task("M01", status="pending")], repo=False)
    write_policy(root)
    data = json.loads((root / "policy.json").read_text())
    data["budget"] = {"max_tokens_per_task": tokens, "warn_at": warn}
    (root / "policy.json").write_text(json.dumps(data))
    return root


class PolicySection(unittest.TestCase):
    def test_defaults_are_off(self):
        self.assertIsNone(policy.budget({"enabled": False})["max_tokens_per_task"])
        self.assertIsNone(policy.budget(policy._merge(policy.DEFAULTS, {}) | {"enabled": True})
                          ["max_tokens_per_task"])

    def test_validation(self):
        good = {"version": 1, "budget": {"max_tokens_per_task": 500_000, "warn_at": 0.75}}
        self.assertEqual(policy.policy_errors(good), [])
        for bad in ({"max_tokens_per_task": 10}, {"max_tokens_per_task": "lots"},
                    {"warn_at": 0}, {"warn_at": True}, {"limit": 5}):
            errors = policy.policy_errors({"version": 1, "budget": bad})
            self.assertTrue(errors, bad)

    def test_invalid_values_never_enforce(self):
        loaded = {"enabled": True, "budget": {"max_tokens_per_task": -5, "warn_at": 9}}
        self.assertEqual(policy.budget(loaded), {"max_tokens_per_task": None, "warn_at": 0.8})


class UsageStore(unittest.TestCase):
    def test_sessions_replace_manual_entries_add(self):
        root = Path(tempfile.mkdtemp())
        runs.record_usage(root, "M01", 1_000, session="a")
        runs.record_usage(root, "M01", 3_000, session="a")
        runs.record_usage(root, "M01", 2_000, session="a")  # never lowers a session total
        runs.record_usage(root, "M01", 500, session="b")
        runs.record_usage(root, "M01", 250)
        runs.record_usage(root, "M01", 250)
        self.assertEqual(runs.usage_total(root, "M01"), 3_000 + 500 + 500)
        self.assertEqual(runs.summary(root, "M01")["tokens"], 4_000)

    def test_rejects_negative(self):
        with self.assertRaises(Exception):
            runs.record_usage(Path(tempfile.mkdtemp()), "M01", -1)


class Checkpoint(unittest.TestCase):
    def test_used_budget_refuses_another_start(self):
        root = budget_project()
        runs.record_usage(root, "M01", 10_000, session="s")
        result = state.check_transition(root, None, "M01", "in_progress")
        self.assertFalse(result["ok"])
        self.assertIn("token budget used (10,000/10,000)", result["errors"][0])
        self.assertIn("budget", result["requires"])

    def test_near_budget_warns(self):
        root = budget_project()
        runs.record_usage(root, "M01", 8_500, session="s")
        result = state.check_transition(root, None, "M01", "in_progress")
        self.assertTrue(result["ok"], result["errors"])
        self.assertTrue(any("8,500 of 10,000 tokens" in warning for warning in result["warnings"]))

    def test_no_budget_no_check(self):
        root = project([task("M01", status="pending")], repo=False)
        write_policy(root)
        runs.record_usage(root, "M01", 10_000_000, session="s")
        self.assertTrue(state.check_transition(root, None, "M01", "in_progress")["ok"])

    def test_show_reports_tokens(self):
        root = budget_project()
        runs.record_usage(root, "M01", 1_234, session="s")
        shown = state.status_of(root, "M01")
        self.assertEqual((shown["tokens"], shown["max_tokens"]), (1_234, 10_000))


class Dispatch(unittest.TestCase):
    def test_a_ready_task_over_budget_is_blocked(self):
        from core import dispatch
        root = budget_project(tasks=[task("M01", status="pending")])
        (root / "tasks").mkdir(exist_ok=True)
        (root / "tasks" / "M01.md").write_text("brief")
        runs.record_usage(root, "M01", 20_000, session="s")
        report = dispatch.plan(root)
        self.assertEqual(report["waves"], [])
        self.assertIn("token budget used", report["blocked"][0]["reason"])




if __name__ == "__main__":
    unittest.main()
