"""core/cycles.py: stages as cycles with progress, gates and burndown."""
from __future__ import annotations

import datetime as dt
import unittest

from dash_helpers import sample_project

from core import cycles

TODAY = dt.date(2026, 10, 29)


class CyclesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_project()
        self.model = cycles.build(self.root, today=TODAY)

    def test_cycles_follow_stages(self) -> None:
        self.assertEqual(len(self.model["cycles"]), 4)
        foundation = self.model["cycles"][0]
        self.assertEqual(foundation["status"], "completed")
        self.assertEqual(foundation["done"], 2)
        self.assertEqual(foundation["total"], 2)
        self.assertEqual(foundation["progress"], 1.0)
        self.assertTrue(foundation["exit_gates"])
        self.assertTrue(all(gate["passed"] for gate in foundation["exit_gates"]))

    def test_active_cycle_and_burndown(self) -> None:
        self.assertIn(self.model["active"], [cycle["id"] for cycle in self.model["cycles"]])
        active = next(cycle for cycle in self.model["cycles"] if cycle["id"] == self.model["active"])
        self.assertEqual(active["status"], "active")
        self.assertTrue(active["burndown"])
        cycle = self.model["cycles"][1]
        self.assertIn("estimate_hours", cycle)
        self.assertIn("actual_hours", cycle)
        self.assertIn("tasks_open", cycle)

    def test_totals(self) -> None:
        self.assertEqual(self.model["totals"]["cycles"], 4)
        self.assertGreaterEqual(self.model["totals"]["done"], 2)
        self.assertGreaterEqual(self.model["totals"]["tasks"], 8)


if __name__ == "__main__":
    unittest.main()
