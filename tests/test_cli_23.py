"""tools/pages.py, tools/intake.py and tools/templates.py (2.3 CLI parity)."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest

from dash_helpers import PACKAGE, sample_project


def run_tool(name, *args):
    return subprocess.run([sys.executable, str(PACKAGE / "tools" / name), *args],
                          capture_output=True, text=True)


class PagesCliTest(unittest.TestCase):
    def test_pages_cli(self) -> None:
        root = sample_project()
        listing = run_tool("pages.py", "list", "--json", "--root", str(root))
        self.assertEqual(listing.returncode, 0, listing.stderr)
        value = json.loads(listing.stdout)
        self.assertGreater(value["counts"]["pages"], 5)
        path = value["pages"][0]["path"]
        shown = run_tool("pages.py", "show", path, "--json", "--root", str(root))
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("text", json.loads(shown.stdout))
        searched = run_tool("pages.py", "search", "contract", "--json", "--root", str(root))
        self.assertEqual(searched.returncode, 0)
        self.assertIn("results", json.loads(searched.stdout))
        fav = run_tool("pages.py", "favorite", "add", path, "--root", str(root))
        self.assertEqual(fav.returncode, 0)
        favorites = run_tool("pages.py", "favorites", "--json", "--root", str(root))
        self.assertIn(path, json.loads(favorites.stdout)["favorites"])


class IntakeCliTest(unittest.TestCase):
    def test_add_accept_reject(self) -> None:
        root = sample_project()
        template = root / "template.json"
        template.write_text(json.dumps({"id": "feature", "name": "Feature",
                                        "scope_write": ["docs/"], "acceptance": ["A1"],
                                        "gates": ["board-check"]}), encoding="utf-8")
        saved = run_tool("templates.py", "save", "--json", str(template), "--root", str(root))
        self.assertEqual(saved.returncode, 0, saved.stderr)
        added = run_tool("intake.py", "add", "--title", "CLI proposal", "--root", str(root))
        self.assertEqual(added.returncode, 0, added.stderr)
        entry = json.loads(added.stdout)
        accepted = run_tool("intake.py", "accept", entry["id"], "--stage", "surface",
                            "--template", "feature", "--note", "go", "--root", str(root))
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        result = json.loads(accepted.stdout)
        self.assertEqual(result["intake"]["status"], "accepted")
        board = json.loads((root / "board.json").read_text(encoding="utf-8"))
        self.assertTrue(any(task["id"] == result["task"]["id"] for task in board["tasks"]))
        listed = run_tool("intake.py", "list", "--json", "--root", str(root))
        self.assertEqual(listed.returncode, 0)
        self.assertIn("entries", json.loads(listed.stdout))


class TemplatesCliTest(unittest.TestCase):
    def test_save_from_task_list_delete(self) -> None:
        root = sample_project()
        saved = run_tool("templates.py", "save", "--from-task", "F-01", "--id", "from-f01",
                         "--name", "From F-01", "--root", str(root))
        self.assertEqual(saved.returncode, 0, saved.stderr)
        listing = run_tool("templates.py", "list", "--json", "--root", str(root))
        self.assertIn("from-f01", listing.stdout)
        shown = run_tool("templates.py", "show", "from-f01", "--json", "--root", str(root))
        self.assertEqual(shown.returncode, 0)
        self.assertEqual(json.loads(shown.stdout)["gates"], ["layout"])
        deleted = run_tool("templates.py", "delete", "from-f01", "--root", str(root))
        self.assertEqual(deleted.returncode, 0)


if __name__ == "__main__":
    unittest.main()
