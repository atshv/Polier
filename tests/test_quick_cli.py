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


ACCEPT = "WHEN the input is empty, THEN bm exits 2 with a message"


def quick(root, *args, accept=True):
    extra = ["--accept", ACCEPT] if accept else []
    return run_tool("quick.py", "new", *args, *extra, "--root", str(root))


class QuickCliTest(unittest.TestCase):
    def test_creates_task_and_brief_that_pass_check(self):
        root = copy()
        result = quick(root, "Fix empty input crash", "--scope", "bm/cli.py", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual((payload["ok"], payload["task"]), (True, "M07"))
        entry = json.loads((root / "board.json").read_text())["tasks"][-1]
        self.assertEqual((entry["track"], entry["status"], entry["scope_write"], entry["acceptance"]),
                         ("quick", "pending", ["bm/cli.py"], ["A1"]))
        self.assertEqual(entry["gates"], ["lint", "types", "tests", "cli-smoke"])  # M03, the last to touch it
        self.assertEqual(entry["satisfies"], ["D1", "D2"])  # M03's
        brief = (root / "tasks" / "M07.md").read_text()
        self.assertIn("A1 " + ACCEPT, brief)
        check = run_tool("check.py", str(root))
        named = [line for line in (check.stdout + check.stderr).splitlines() if "M07" in line]
        self.assertEqual(named, [])  # no finding names the new task

    def test_refusal_exits_1_with_reasons_and_next(self):
        root = copy()
        result = quick(root, "Bump dependency", "--scope", "pyproject.toml", "--json")
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["reasons"])
        self.assertIn("pl_change new", payload["next"])

    def test_record_path_is_refused(self):
        result = quick(copy(), "Add web platform", "--scope", "factory.json", "--json")
        self.assertEqual(result.returncode, 1)
        self.assertIn("factory.json", " ".join(json.loads(result.stdout)["reasons"]))

    def test_build_station_open_refuses_in_text_mode(self):
        result = quick(copy("in_progress"), "Fix it", "--scope", "bm/cli.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("build station", result.stdout)

    def test_accept_is_required(self):
        root = copy()
        result = quick(root, "Fix it", "--scope", "bm/cli.py", accept=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--accept", result.stderr)
        self.assertEqual(len(json.loads((root / "board.json").read_text())["tasks"]), 6)

    def test_satisfies_needed_when_nobody_touched_the_file(self):
        root = copy()
        (root / "bm" / "new.py").write_text("y = 1\n")
        refused = quick(root, "Fix it", "--scope", "bm/new.py")
        self.assertEqual(refused.returncode, 2)
        self.assertIn("--satisfies", refused.stderr)
        self.assertEqual(quick(root, "Fix it", "--scope", "bm/new.py", "--satisfies", "D9").returncode, 2)
        self.assertEqual(quick(root, "Fix it", "--scope", "bm/new.py", "--satisfies", "D1").returncode, 0)

    def test_no_board_is_usage_error(self):
        result = quick(tempfile.mkdtemp(), "Fix it", "--scope", "x.py")
        self.assertEqual(result.returncode, 2)

    def test_quick_task_follows_the_state_machine(self):
        root = copy()
        quick(root, "Fix empty input crash", "--scope", "bm/cli.py")
        start = run_tool("state.py", "check", "M07", "in_progress", "--root", str(root))
        self.assertEqual(start.returncode, 0, start.stdout + start.stderr)
        self.assertIn("M07", start.stdout)
        # the same refusal as an ordinary pending task gets for a jump to done
        quick_done = run_tool("state.py", "check", "M07", "done", "--root", str(root))
        plain_done = run_tool("state.py", "check", "M05", "done", "--root", str(root))
        self.assertEqual(quick_done.returncode, 1)
        self.assertEqual(plain_done.returncode, quick_done.returncode)


if __name__ == "__main__":
    unittest.main()
