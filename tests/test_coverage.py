"""core/coverage.py: requirement definitions, tasks and evidence."""
from __future__ import annotations

import json
import unittest

from dash_helpers import sample_project

from core import coverage


class CoverageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_project()
        self.model = coverage.build(self.root)

    def test_definitions_and_states(self) -> None:
        summary = self.model["summary"]
        self.assertGreaterEqual(summary["defined"], 5)
        states = {requirement["id"]: requirement["state"] for requirement in self.model["requirements"]}
        self.assertEqual(states.get("D1"), "covered")
        self.assertIn("D3", states)
        self.assertIn(states["D3"], ("open", "partial", "covered"))
        self.assertEqual(summary["covered"] + summary["partial"] + summary["open"] + summary["missing"],
                         len(self.model["requirements"]))

    def test_undefined_requirement_is_reported(self) -> None:
        board = json.loads((self.root / "board.json").read_text(encoding="utf-8"))
        board["schema_version"] = "1.1"
        board["tasks"][0]["satisfies"] = ["D99"]
        (self.root / "board.json").write_text(json.dumps(board, indent=2) + "\n", encoding="utf-8")
        model = coverage.build(self.root)
        self.assertIn("D99", model["summary"]["undefined"])
        row = next(requirement for requirement in model["requirements"] if requirement["id"] == "D99")
        self.assertFalse(row["defined"])

    def test_task_rows_carry_evidence(self) -> None:
        for requirement in self.model["requirements"]:
            for task in requirement["tasks"]:
                self.assertIn("evidence", task)
                self.assertIn("status", task)


if __name__ == "__main__":
    unittest.main()
