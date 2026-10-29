"""Token budget: policy section, usage store, checkpoint and the Claude Code transcript reader."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from core import policy, runs, state

from .fixtures import project, task, write_policy

HOOK = Path(__file__).resolve().parents[2] / "adapters" / "claude-code" / "hook.py"


def load_hook():
    spec = importlib.util.spec_from_file_location("polier_hook_budget", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


class Transcript(unittest.TestCase):
    def write(self, entries) -> Path:
        path = Path(tempfile.mkdtemp()) / "t.jsonl"
        path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\nnot json\n")
        return path

    def test_counts_each_message_once_without_cache_reads(self):
        hook = load_hook()
        usage = {"input_tokens": 100, "output_tokens": 50, "cache_creation_input_tokens": 10,
                 "cache_read_input_tokens": 99_999}
        path = self.write([
            {"type": "user", "message": {"role": "user", "content": "hi"}},
            {"type": "assistant", "timestamp": "2026-10-29T10:00:00.000Z",
             "message": {"id": "m1", "usage": {"input_tokens": 100, "output_tokens": 5}}},
            {"type": "assistant", "timestamp": "2026-10-29T10:00:01.000Z",
             "message": {"id": "m1", "usage": usage}},
            {"type": "assistant", "timestamp": "2026-10-29T11:00:00.000Z",
             "message": {"id": "m2", "usage": {"input_tokens": 1_000, "output_tokens": 0}}},
        ])
        self.assertEqual(hook.transcript_tokens(path), 160 + 1_000)
        since = hook._parse_time("2026-10-29T10:30:00+00:00")
        self.assertEqual(hook.transcript_tokens(path, since=since), 1_000)
        self.assertEqual(hook.transcript_tokens(path.parent / "missing.jsonl"), 0)

    def test_stop_records_usage_and_warns_at_budget(self):
        hook = load_hook()
        root = budget_project(tokens=1_000, tasks=[task("M01", status="in_progress")])
        path = self.write([{"type": "assistant", "timestamp": "2026-10-29T10:00:00Z",
                            "message": {"id": "m1", "usage": {"input_tokens": 1_200}}}])
        event = {"cwd": str(root), "session_id": "s1", "transcript_path": str(path)}
        output = hook.stop(event, {"POLIER_TASK": "M01", "POLIER_STOP_CHECK": "0"})
        self.assertEqual(runs.usage_total(root, "M01"), 1_200)
        self.assertIn("used its token budget", output["systemMessage"])

    def test_usage_can_be_switched_off(self):
        hook = load_hook()
        root = budget_project(tasks=[task("M01", status="in_progress")])
        path = self.write([{"type": "assistant", "message": {"id": "m1", "usage": {"input_tokens": 5}}}])
        event = {"cwd": str(root), "session_id": "s1", "transcript_path": str(path)}
        hook.stop(event, {"POLIER_TASK": "M01", "POLIER_STOP_CHECK": "0", "POLIER_USAGE": "0"})
        self.assertEqual(runs.usage_total(root, "M01"), 0)


if __name__ == "__main__":
    unittest.main()
