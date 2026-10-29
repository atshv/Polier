"""core/automations.py: rule validation and dry-run evaluation."""
from __future__ import annotations

import json
import unittest

from dash_helpers import sample_project

from core import automations
from core.errors import PolierError

RULES = {
    "version": 1,
    "rules": [
        {"id": "gate-failed", "name": "Failed gate", "enabled": True,
         "when": {"kind": "gate_failed"},
         "actions": [{"type": "state", "status": "blocked", "note": "fix the gate"}]},
        {"id": "review-waiting", "name": "Review waiting", "enabled": True,
         "when": {"kind": "review_ready"},
         "actions": [{"type": "session", "role": "reviewer"}]},
        {"id": "stage-decision", "name": "Stage decision", "enabled": True,
         "when": {"kind": "stage_decision_pending"},
         "actions": [{"type": "open"}]},
        {"id": "blocked", "name": "Blocked too long", "enabled": True,
         "when": {"kind": "task_blocked", "params": {"min_days": 0}},
         "actions": [{"type": "state", "status": "in_progress", "note": "unblock"}]},
    ],
}


def prepare(root) -> None:
    board = json.loads((root / "board.json").read_text(encoding="utf-8"))
    for task in board["tasks"]:
        if task["id"] == "ENG-01":
            task["status"] = "blocked"
            task["blocked_reason"] = "waits for the spike"
        if task["id"] == "ENG-02":
            task["status"] = "review"
    for stage in board.get("stages") or []:
        if stage.get("id") == "foundation":
            stage["owner_decision"] = "pending"
    (root / "board.json").write_text(json.dumps(board, indent=2) + "\n", encoding="utf-8")
    evidence = root / "reviews" / "evidence"
    (evidence / "F-01-layout-failing.json").write_text(json.dumps({
        "task": "F-01", "gate": "layout", "command": "layout", "exit_code": 1,
        "result": "fail", "started": "2026-10-29T10:00:00+00:00",
        "finished": "2026-10-29T10:01:00+00:00", "log": "missing.log",
        "log_sha256": "0" * 64, "commit": None, "dirty": True, "slot": None,
        "exclusive": [], "lock_wait_s": 0, "lock_warning": None}, indent=2) + "\n",
        encoding="utf-8")


class AutomationsTest(unittest.TestCase):
    def test_validation(self) -> None:
        root = sample_project()
        value = automations.save(root, RULES)
        self.assertEqual(len(value["rules"]), 4)
        self.assertEqual(automations.errors(value), [])
        with self.assertRaises(PolierError):
            automations.save(root, {"version": 1, "rules": [{"id": "Bad"}]})
        with self.assertRaises(PolierError):
            automations.save(root, {"version": 1, "rules": [
                {"id": "x", "name": "x", "when": {"kind": "nope"}, "actions": [{"type": "note"}]}]})

    def test_dry_run_matches_rules(self) -> None:
        root = sample_project()
        prepare(root)
        automations.save(root, RULES)
        value = automations.evaluate(root)
        self.assertTrue(value["dry_run"])
        kinds = {match["event"]["kind"] for match in value["matches"]}
        self.assertIn("gate_failed", kinds)
        self.assertIn("task_blocked", kinds)
        self.assertIn("review_ready", kinds)
        self.assertIn("stage_decision_pending", kinds)
        self.assertTrue(all(match["actions"] for match in value["matches"]))
        rules = {match["rule"] for match in value["matches"]}
        self.assertIn("gate-failed", rules)

    def test_disabled_rules_are_skipped(self) -> None:
        root = sample_project()
        prepare(root)
        automations.save(root, {"version": 1, "rules": [
            {"id": "gate-failed", "name": "x", "enabled": False,
             "when": {"kind": "gate_failed"}, "actions": [{"type": "note", "text": "x"}]}]})
        self.assertEqual(automations.evaluate(root)["total"], 0)


if __name__ == "__main__":
    unittest.main()
