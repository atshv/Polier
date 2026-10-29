"""core/plan_edit.py: validated plan edits (tasks, dependencies, stage decisions)."""
from __future__ import annotations

import json
import unittest

from dash_helpers import sample_project

from core import board, plan_edit
from core.errors import PolierError


class PlanEditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_project()

    def _board(self) -> dict:
        return json.loads((self.root / "board.json").read_text(encoding="utf-8"))

    def _create(self, payload: dict) -> dict:
        return plan_edit.create_task(self.root, payload)

    def test_create_update_and_delete_task(self) -> None:
        task = self._create({
            "id": "DASH-01", "title": "Dashboard test task", "goal": "Do a thing.",
            "stage": "surface", "complexity": 2,
            "scope_write": ["docs/dashboard.md"], "acceptance": ["A1"], "gates": ["board-check"],
        })
        self.assertEqual(task["status"], "pending")
        board_data = self._board()
        self.assertEqual(len(board_data["tasks"]), 9)
        self.assertTrue(any(entry["id"] == "DASH-01" for entry in board_data["tasks"]))
        updated = plan_edit.update_task(self.root, "DASH-01", {
            "title": "Dashboard test task (edited)",
            "depends_on": ["F-01", "F-02"],
            "scope_write": ["docs/dashboard.md", "docs/"],
        })
        self.assertEqual(updated["title"], "Dashboard test task (edited)")
        self.assertEqual(updated["depends_on"], ["F-01", "F-02"])
        result = plan_edit.delete_task(self.root, "DASH-01")
        self.assertTrue(result["deleted"])
        self.assertFalse(any(entry["id"] == "DASH-01" for entry in self._board()["tasks"]))

    def test_dependency_cycle_is_refused(self) -> None:
        for task_id in ("DASH-01", "DASH-02"):
            self._create({
                "id": task_id, "title": f"Task {task_id}", "goal": "Do it.", "stage": "surface",
                "scope_write": ["docs/"], "acceptance": ["A1"], "gates": [],
            })
        plan_edit.update_task(self.root, "DASH-01", {"depends_on": ["DASH-02"]})
        with self.assertRaises(PolierError):
            plan_edit.update_task(self.root, "DASH-02", {"depends_on": ["DASH-01"]})

    def test_create_needs_required_fields_and_free_id(self) -> None:
        with self.assertRaises(PolierError):
            self._create({"id": "DASH-01", "title": "No goal", "stage": "surface"})
        self._create({"id": "DASH-01", "title": "A task", "goal": "Do it.", "stage": "surface",
                      "scope_write": ["docs/"], "acceptance": ["A1"], "gates": ["board-check"]})
        with self.assertRaises(PolierError):
            self._create({"id": "DASH-01", "title": "A task", "goal": "Do it.", "stage": "surface",
                          "scope_write": ["docs/"], "acceptance": ["A1"], "gates": ["board-check"]})
        with self.assertRaises(PolierError):
            self._create({"id": "DASH-02", "title": "Another task", "goal": "Do it.", "stage": "no-such-stage",
                          "scope_write": ["docs/"], "acceptance": ["A1"], "gates": ["board-check"]})

    def test_done_task_is_not_plan_editable_and_dependents_block_deletion(self) -> None:
        with self.assertRaises(PolierError):
            plan_edit.update_task(self.root, "F-01", {"title": "renamed"})
        with self.assertRaises(PolierError):
            plan_edit.delete_task(self.root, "F-01")

    def test_stage_decision(self) -> None:
        stage = plan_edit.set_stage_decision(self.root, "foundation", "stop")
        self.assertEqual(stage["owner_decision"], "stop")
        stage = plan_edit.set_stage_decision(self.root, "foundation", "continue")
        self.assertEqual(stage["owner_decision"], "continue")
        with self.assertRaises(PolierError):
            plan_edit.set_stage_decision(self.root, "foundation", "maybe")

    def test_suggest_id_skips_used_ids(self) -> None:
        board_data = self._board()
        suggestion = plan_edit.suggest_id(board_data, "DASH")
        self.assertEqual(suggestion, "DASH-01")
        self.assertTrue(board.board_errors(board_data) == [])


if __name__ == "__main__":
    unittest.main()
