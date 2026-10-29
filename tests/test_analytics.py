"""core/analytics.py: KPIs derived from runs, evidence and worklog."""
from __future__ import annotations

import datetime as dt
import unittest

from dash_helpers import sample_project

from core import analytics

TODAY = dt.date(2026, 10, 29)


class AnalyticsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_project()
        self.model = analytics.build(self.root, today=TODAY)

    def test_kpis(self) -> None:
        kpis = self.model["kpis"]
        self.assertEqual(kpis["tasks_total"], 8)
        self.assertGreaterEqual(kpis["tasks_done"], 2)
        self.assertIn("status_counts", kpis)
        self.assertIsNotNone(kpis["gate_pass_rate"])
        self.assertGreaterEqual(kpis["gate_total"], 1)
        self.assertIn("rework_rate", kpis)
        self.assertIn("blocked_avg_days", kpis)

    def test_series(self) -> None:
        self.assertEqual(len(self.model["throughput"]), 12)
        self.assertGreaterEqual(self.model["throughput_total"], 2)
        self.assertIn("cycle_time", self.model)
        self.assertIn("gate_results", self.model)
        self.assertIn("effort", self.model)
        self.assertIn("sessions", self.model)

    def test_effort_totals(self) -> None:
        self.assertIn("totals", self.model["effort"])
        self.assertIn("stages", self.model["effort"])
        self.assertIn("actual_hours", self.model["effort"]["totals"])


if __name__ == "__main__":
    unittest.main()
