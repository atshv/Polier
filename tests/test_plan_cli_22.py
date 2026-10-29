"""tools/plan.py: planning dates (2.2)."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest

from dash_helpers import PACKAGE, sample_project


def run_tool(*args):
    return subprocess.run([sys.executable, str(PACKAGE / "tools" / "plan.py"), *args],
                          capture_output=True, text=True)


class PlanDatesCliTest(unittest.TestCase):
    def test_dates_are_set_and_upgrade_the_board(self) -> None:
        root = sample_project()
        result = run_tool("update", "ENG-01", "--root", str(root),
                          "--planned-start", "2026-12-01", "--target", "2026-12-10")
        self.assertEqual(result.returncode, 0, result.stderr)
        board = json.loads((root / "board.json").read_text(encoding="utf-8"))
        self.assertEqual(board["schema_version"], "1.2")
        task = next(entry for entry in board["tasks"] if entry["id"] == "ENG-01")
        self.assertEqual(task["planned_start"], "2026-12-01")
        self.assertEqual(task["target"], "2026-12-10")

    def test_invalid_date_order_is_refused(self) -> None:
        root = sample_project()
        result = run_tool("update", "ENG-01", "--root", str(root),
                          "--planned-start", "2026-12-10", "--target", "2026-12-01")
        self.assertEqual(result.returncode, 1)
        self.assertIn("target must not be before", result.stderr)

    def test_dates_can_be_cleared_with_json_null(self) -> None:
        root = sample_project()
        run_tool("update", "ENG-01", "--root", str(root),
                 "--planned-start", "2026-12-01", "--target", "2026-12-10")
        payload = root / "clear.json"
        payload.write_text(json.dumps({"planned_start": None, "target": None}), encoding="utf-8")
        result = run_tool("update", "ENG-01", "--root", str(root), "--json", str(payload))
        self.assertEqual(result.returncode, 0, result.stderr)
        board = json.loads((root / "board.json").read_text(encoding="utf-8"))
        task = next(entry for entry in board["tasks"] if entry["id"] == "ENG-01")
        self.assertNotIn("planned_start", task)
        self.assertNotIn("target", task)


if __name__ == "__main__":
    unittest.main()
