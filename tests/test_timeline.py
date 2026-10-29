"""core/timeline.py: derived schedule, dates and critical path."""
from __future__ import annotations

import datetime as dt
import json
import unittest

from dash_helpers import sample_project

from core import plan_edit, settings, timeline

TODAY = dt.date(2026, 11, 2)


class TimelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_project()

    def test_timeline_has_lanes_tasks_and_critical_path(self) -> None:
        model = timeline.build(self.root, today=TODAY)
        self.assertEqual(model["today"], "2026-11-02")
        self.assertEqual(model["hours_per_day"], 4.0)
        self.assertGreaterEqual(len(model["stages"]), 4)
        self.assertGreater(model["totals"]["tasks"], 0)
        self.assertTrue(model["critical_path"])
        self.assertTrue(all(lane["tasks"] or lane["start"] for lane in model["stages"]))
        first = next(task for lane in model["stages"] for task in lane["tasks"])
        self.assertIn("start", first)
        self.assertIn("end", first)
        self.assertIn("critical", first)
        json.dumps(model)  # serializable
        self.assertEqual(model["totals"]["scheduled"], model["totals"]["tasks"])

    def test_explicit_dates_override_the_auto_schedule(self) -> None:
        plan_edit.update_task(self.root, "ENG-01", {
            "planned_start": "2026-12-01", "target": "2026-12-10"})
        board = json.loads((self.root / "board.json").read_text(encoding="utf-8"))
        self.assertEqual(board["schema_version"], "1.2")
        model = timeline.build(self.root, today=TODAY)
        task = next(task for lane in model["stages"] for task in lane["tasks"]
                    if task["id"] == "ENG-01")
        self.assertEqual(task["start"], "2026-12-01")
        self.assertEqual(task["end"], "2026-12-10")
        self.assertTrue(task["explicit"])
        self.assertEqual(model["totals"]["explicit"], 1)

    def test_hours_per_day_comes_from_settings(self) -> None:
        settings.save(self.root, {"defaults": {"me": "owner", "hours_per_day": 8}})
        model = timeline.build(self.root, today=TODAY)
        task = next(task for lane in model["stages"] for task in lane["tasks"])
        self.assertEqual(model["hours_per_day"], 8.0)
        self.assertGreaterEqual(task["hours"], 0.5)

    def test_tasks_outside_a_declared_stage_are_unscheduled(self) -> None:
        board = json.loads((self.root / "board.json").read_text(encoding="utf-8"))
        board["tasks"].append({
            "id": "GHOST-01", "title": "Ghost task", "goal": "Do it.", "status": "pending",
            "depends_on": [], "complexity": 2, "stage": "no-such-stage",
            "scope_write": ["docs/"], "acceptance": ["A1"], "gates": ["board-check"]})
        model = timeline.build(self.root, board=board, today=TODAY)
        self.assertIn("GHOST-01", model["unscheduled"])
        self.assertEqual(model["totals"]["scheduled"], model["totals"]["tasks"] - 1)

    def test_done_tasks_are_backfilled_from_run_events(self) -> None:
        model = timeline.build(self.root, today=TODAY)
        done = next(task for lane in model["stages"] for task in lane["tasks"]
                    if task["id"] == "F-01")
        self.assertLessEqual(done["end"], TODAY.isoformat())


if __name__ == "__main__":
    unittest.main()
