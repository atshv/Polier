"""tools/quick.py on a copy of the minimal-cli fixture."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import PACKAGE, run_tool

FIXTURE = PACKAGE / "tests" / "fixtures" / "minimal-cli"


def copy(build: str = "done") -> Path:
    root = Path(tempfile.mkdtemp(prefix="pl-quick-")) / "p"
    shutil.copytree(FIXTURE, root)
    (root / "factory.json").write_text(json.dumps({"stations": {"build": {"status": build}}, "items": {}}))
    (root / "factory.json").write_text(json.dumps({
        "factory_version": "1", "platforms": ["cli"], "traits": [], "resolved_traits": [],
        "stations": {"build": {"status": build}}, "items": {}, "history": []}))
    (root / "bm").mkdir(exist_ok=True)
    (root / "bm" / "cli.py").write_text("x = 1\n")
    return root


def quick(root, *args):
    return run_tool("quick.py", "new", *args, "--root", str(root))


class QuickCliTest(unittest.TestCase):
    def test_creates_task_and_brief_that_pass_check(self):
        root = copy()
        result = quick(root, "Fix empty input crash", "--scope", "bm/cli.py", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual((payload["ok"], payload["task"]), (True, "M07"))
        board = json.loads((root / "board.json").read_text())
        entry = board["tasks"][-1]
        self.assertEqual((entry["track"], entry["status"], entry["scope_write"]),
                         ("quick", "pending", ["bm/cli.py"]))
        self.assertEqual(entry["gates"], ["lint", "types", "tests", "cli-smoke"])  # gates of M03, last to touch it
        self.assertTrue((root / "tasks" / "M07.md").is_file())
        check = run_tool("check.py", str(root))
        self.assertNotIn("M07", check.stdout + check.stderr, check.stdout + check.stderr)

    def test_refusal_exits_1_with_reasons_and_next(self):
        root = copy()
        result = quick(root, "Bump dependency", "--scope", "pyproject.toml", "--json")
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["reasons"])
        self.assertIn("pl_change new", payload["next"])

    def test_build_station_open_refuses_in_text_mode(self):
        result = quick(copy("in_progress"), "Fix it", "--scope", "bm/cli.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("build station", result.stdout)

    def test_no_board_is_usage_error(self):
        result = quick(tempfile.mkdtemp(), "Fix it", "--scope", "x.py")
        self.assertEqual(result.returncode, 2)

    def test_quick_task_follows_the_state_machine(self):
        root = copy()
        quick(root, "Fix empty input crash", "--scope", "bm/cli.py")
        shown = run_tool("state.py", "check", "M07", "in_progress", "--root", str(root))
        self.assertIn(shown.returncode, (0, 1))
        self.assertNotIn("Traceback", shown.stderr)
        self.assertIn("M07", shown.stdout)


if __name__ == "__main__":
    unittest.main()
