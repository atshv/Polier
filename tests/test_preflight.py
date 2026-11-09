"""core/preflight.py and tools/preflight.py: checks before work starts, nothing changed."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from core.preflight import run
from tests.helpers import make_project, run_tool, task


def levels(result: dict) -> dict:
    return {c["check"]: c["level"] for c in result["checks"]}


class Preflight(unittest.TestCase):
    def test_outside_a_project(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        result = run(folder)
        self.assertTrue(result["ok"])
        self.assertEqual(levels(result)["project"], "warn")
        self.assertEqual(levels(result)["python"], "ok")

    def test_project_without_git_fails_with_a_fix(self):
        root = make_project([task()])
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        shutil.rmtree(root / ".git", ignore_errors=True)
        result = run(root / "src")
        self.assertFalse(result["ok"])
        repo = next(c for c in result["checks"] if c["check"] == "repository")
        self.assertEqual(repo["level"], "fail")
        self.assertIn("git init", repo["fix"])

    def test_broken_board_and_stale_status(self):
        root = make_project([task()])
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        subprocess.run(["git", "init", "-q"], cwd=root, check=False)
        board = json.loads((root / "board.json").read_text())
        board["mystery"] = 1
        (root / "board.json").write_text(json.dumps(board))
        result = run(root)
        self.assertEqual(levels(result)["board"], "fail")
        self.assertEqual(levels(result)["status page"], "warn")
        self.assertEqual(levels(result)["line"], "warn")

    def test_cli(self):
        root = make_project([task()])
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        result = run_tool("preflight.py", str(root), "--json")
        data = json.loads(result.stdout)
        self.assertIn("checks", data)
        self.assertEqual(result.returncode, 0 if data["ok"] else 1)


if __name__ == "__main__":
    unittest.main()
