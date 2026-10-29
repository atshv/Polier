"""core/settings.py: committed dashboard.json (features, labels, defaults)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dash_helpers import sample_project

from core import settings
from core.errors import PolierError


class SettingsTest(unittest.TestCase):
    def test_defaults_and_file_roundtrip(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="pl-settings-"))
        value = settings.load(root)
        self.assertEqual(value["version"], 1)
        self.assertTrue(settings.features(value)["inbox"])
        self.assertEqual(settings.features(value)["timeline"], False)
        saved = settings.save(root, {"features": {"timeline": True}})
        self.assertTrue(settings.enabled(saved, "timeline"))
        self.assertTrue((root / "dashboard.json").is_file())
        self.assertEqual(settings.load(root)["features"]["timeline"], True)

    def test_validation(self) -> None:
        self.assertTrue(settings.errors({"version": 7}))
        self.assertTrue(settings.errors({"features": {"unknown": True}}))
        self.assertTrue(settings.errors({"labels": [{"id": "Bad", "title": "x",
                                                   "color": "red", "group": "type"}]}))
        self.assertTrue(settings.errors({"labels": [{"id": "bug", "title": "x",
                                                   "color": "pink", "group": "type"}]}))
        self.assertTrue(settings.errors({"labels": [{"id": "bug", "title": "x",
                                                   "color": "red", "group": "nope"}]}))
        with self.assertRaises(PolierError):
            settings.save(tempfile.mkdtemp(), {"defaults": {"me": ""}})

    def test_label_lifecycle_and_usage(self) -> None:
        root = sample_project()
        settings.add_label(root, {"id": "docs", "title": "Docs", "color": "blue", "group": "theme"})
        self.assertEqual(settings.label_map(settings.load(root))["docs"]["title"], "Docs")
        updated = settings.update_label(root, "docs", {"title": "Documentation"})
        self.assertEqual(updated["label"]["title"], "Documentation")
        board = json.loads((root / "board.json").read_text(encoding="utf-8"))
        board["schema_version"] = "1.1"
        board["tasks"][0]["labels"] = ["docs"]
        (root / "board.json").write_text(json.dumps(board, indent=2) + "\n", encoding="utf-8")
        with self.assertRaises(PolierError):
            settings.delete_label(root, "docs")
        result = settings.delete_label(root, "docs", force=True)
        self.assertIn("F-01", result["tasks_updated"])
        board = json.loads((root / "board.json").read_text(encoding="utf-8"))
        self.assertNotIn("docs", board["tasks"][0].get("labels", []))


if __name__ == "__main__":
    unittest.main()
