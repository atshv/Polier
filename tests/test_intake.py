"""core/intake.py: proposal lifecycle and acceptance into the plan."""
from __future__ import annotations

import json
import unittest

from dash_helpers import sample_project

from core import intake, task_templates
from core.errors import PolierError


class IntakeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_project()

    def test_create_update_and_list(self) -> None:
        entry = intake.create(self.root, {"title": "Add a wiki", "description": "Browse docs",
                                          "kind": "idea", "priority": "high"})
        self.assertEqual(entry["id"], "IN-001")
        self.assertEqual(entry["status"], "proposed")
        second = intake.create(self.root, {"title": "Fix the bug", "kind": "issue"})
        self.assertEqual(second["id"], "IN-002")
        updated = intake.update(self.root, entry["id"], {"title": "Add a wiki page",
                                                         "priority": "low"})
        self.assertEqual(updated["title"], "Add a wiki page")
        self.assertEqual(len(intake.load_all(self.root)), 2)
        self.assertEqual(len(intake.load_all(self.root, "proposed")), 2)
        with self.assertRaises(PolierError):
            intake.create(self.root, {"title": "x"})
        with self.assertRaises(PolierError):
            intake.update(self.root, entry["id"], {"status": "accepted"})

    def test_accept_with_template_creates_task(self) -> None:
        task_templates.save(self.root, {"id": "feature", "name": "Feature",
                                        "scope_write": ["docs/"], "acceptance": ["A1"],
                                        "gates": ["board-check"], "complexity": 3,
                                        "labels": ["feature"], "estimate_hours": 4})
        entry = intake.create(self.root, {"title": "Write the docs", "description": "Docs page"})
        result = intake.accept(self.root, entry["id"], task_payload={"stage": "surface"},
                               template="feature", note="go")
        self.assertEqual(result["intake"]["status"], "accepted")
        self.assertEqual(result["intake"]["task"], result["task"]["id"])
        board = json.loads((self.root / "board.json").read_text(encoding="utf-8"))
        task = next(item for item in board["tasks"] if item["id"] == result["task"]["id"])
        self.assertEqual(task["title"], "Write the docs")
        self.assertEqual(task["labels"], ["feature"])
        with self.assertRaises(PolierError):
            intake.accept(self.root, entry["id"], task_payload={"stage": "surface"})

    def test_accept_needs_structure(self) -> None:
        entry = intake.create(self.root, {"title": "No structure"})
        with self.assertRaises(PolierError):
            intake.accept(self.root, entry["id"], task_payload={"stage": "surface"})
        self.assertEqual(intake.get(self.root, entry["id"])["status"], "proposed")

    def test_reject_and_summary(self) -> None:
        entry = intake.create(self.root, {"title": "Reject me"})
        with self.assertRaises(PolierError):
            intake.reject(self.root, entry["id"], note="")
        rejected = intake.reject(self.root, entry["id"], note="not now")
        self.assertEqual(rejected["status"], "rejected")
        summary = intake.summary(self.root)
        self.assertEqual(summary["counts"]["rejected"], 1)
        with self.assertRaises(PolierError):
            intake.reject(self.root, entry["id"], note="again")


if __name__ == "__main__":
    unittest.main()
