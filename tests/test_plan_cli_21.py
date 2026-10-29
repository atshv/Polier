"""tools/plan.py, tools/settings.py and tools/views.py (2.1 CLI parity)."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest

from dash_helpers import PACKAGE, sample_project


def run_tool(name: str, *args):
    result = subprocess.run([sys.executable, str(PACKAGE / "tools" / name), *args],
                            capture_output=True, text=True)
    return result


class PlanCliTest(unittest.TestCase):
    def test_create_update_delete_with_labels_and_estimate(self) -> None:
        root = sample_project()
        created = run_tool("settings.py", "label", "add", "docs", "Docs", "--color", "blue",
                           "--group", "theme", "--root", str(root))
        self.assertEqual(created.returncode, 0, created.stderr)
        result = run_tool("plan.py", "create", "--root", str(root), "--id", "DASH-01",
                          "--title", "Dashboard task", "--goal", "Do a thing.",
                          "--stage", "surface", "--scope-write", "docs/",
                          "--acceptance", "A1", "--gates", "board-check",
                          "--labels", "docs", "--estimate-hours", "4")
        self.assertEqual(result.returncode, 0, result.stderr)
        board = json.loads((root / "board.json").read_text(encoding="utf-8"))
        self.assertEqual(board["schema_version"], "1.1")
        task = next(entry for entry in board["tasks"] if entry["id"] == "DASH-01")
        self.assertEqual(task["labels"], ["docs"])
        self.assertEqual(task["estimate_hours"], 4)
        updated = run_tool("plan.py", "update", "DASH-01", "--root", str(root),
                           "--title", "Dashboard task (edited)", "--estimate-hours", "6")
        self.assertEqual(updated.returncode, 0, updated.stderr)
        board = json.loads((root / "board.json").read_text(encoding="utf-8"))
        task = next(entry for entry in board["tasks"] if entry["id"] == "DASH-01")
        self.assertEqual(task["estimate_hours"], 6)
        deleted = run_tool("plan.py", "delete", "DASH-01", "--root", str(root))
        self.assertEqual(deleted.returncode, 0, deleted.stderr)

    def test_labels_accept_a_comma_list(self) -> None:
        root = sample_project()
        for label in ("docs", "risky"):
            added = run_tool("settings.py", "label", "add", label, label.title(), "--root", str(root))
            self.assertEqual(added.returncode, 0, added.stderr)
        result = run_tool("plan.py", "create", "--root", str(root), "--id", "DASH-03",
                          "--title", "Two labels", "--goal", "Do it.", "--stage", "surface",
                          "--scope-write", "docs/", "--acceptance", "A1", "--gates", "board-check",
                          "--labels", "docs, risky")
        self.assertEqual(result.returncode, 0, result.stderr)
        board = json.loads((root / "board.json").read_text(encoding="utf-8"))
        task = next(entry for entry in board["tasks"] if entry["id"] == "DASH-03")
        self.assertEqual(task["labels"], ["docs", "risky"])

    def test_unknown_label_is_refused(self) -> None:
        root = sample_project()
        result = run_tool("plan.py", "create", "--root", str(root), "--id", "DASH-02",
                          "--title", "No label", "--goal", "Do it.", "--stage", "surface",
                          "--scope-write", "docs/", "--acceptance", "A1", "--gates", "board-check",
                          "--labels", "ghost")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown label", result.stderr)

    def test_stage_decision_and_suggest(self) -> None:
        root = sample_project()
        result = run_tool("plan.py", "stage", "foundation", "decision", "--decision", "stop",
                          "--root", str(root))
        self.assertEqual(result.returncode, 0, result.stderr)
        suggested = run_tool("plan.py", "suggest-id", "--root", str(root), "--prefix", "DASH")
        self.assertEqual(suggested.returncode, 0)
        self.assertTrue(json.loads(suggested.stdout)["id"].startswith("DASH-"))


class SettingsCliTest(unittest.TestCase):
    def test_show_init_feature_me(self) -> None:
        root = sample_project()
        self.assertEqual(run_tool("settings.py", "init", "--root", str(root)).returncode, 0)
        self.assertEqual(run_tool("settings.py", "feature", "timeline", "on",
                                  "--root", str(root)).returncode, 0)
        self.assertEqual(run_tool("settings.py", "me", "lead", "--root", str(root)).returncode, 0)
        shown = run_tool("settings.py", "show", "--json", "--root", str(root))
        value = json.loads(shown.stdout)
        self.assertTrue(value["features"]["timeline"])
        self.assertEqual(value["defaults"]["me"], "lead")


class ViewsCliTest(unittest.TestCase):
    def test_save_list_delete(self) -> None:
        root = sample_project()
        payload = json.dumps({"id": "review-queue", "name": "Review queue", "kind": "table",
                              "filters": [{"field": "status", "op": "any_of",
                                           "value": ["review", "verifying"]}],
                              "group_by": "owner"})
        path = root / "view.json"
        path.write_text(payload, encoding="utf-8")
        self.assertEqual(run_tool("views.py", "save", str(path), "--root", str(root)).returncode, 0)
        listing = run_tool("views.py", "list", "--json", "--root", str(root))
        self.assertIn("review-queue", listing.stdout)
        self.assertEqual(run_tool("views.py", "delete", "review-queue",
                                  "--root", str(root)).returncode, 0)


if __name__ == "__main__":
    unittest.main()
