"""tools/scope_check.py — one test per acceptance criterion of the scope check."""
from __future__ import annotations

import json
import unittest

from helpers import git, make_project, run_tool, task


class ScopeCheck(unittest.TestCase):
    def run_check(self, root, *args):
        return run_tool("scope_check.py", str(root), *args)

    def test_change_inside_scope_passes(self):
        root = make_project([task()])
        (root / "src" / "app.py").write_text("x = 2\n")
        (root / "tests").mkdir()
        (root / "tests" / "test_app.py").write_text("pass\n")
        result = self.run_check(root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SCOPE OK M01", result.stdout)

    def test_change_outside_scope_fails(self):
        root = make_project([task()])
        (root / "README.md").write_text("changed\n")
        result = self.run_check(root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("README.md: outside scope", result.stdout)
        self.assertIn("M01", result.stdout)

    def test_forbidden_wins_over_scope(self):
        root = make_project([task(scope_write=["src/"], scope_write_forbidden=["src/app.py"])])
        (root / "src" / "app.py").write_text("x = 3\n")
        result = self.run_check(root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("src/app.py: forbidden", result.stdout)

    def test_untracked_deleted_staged_and_renamed_count(self):
        root = make_project([task(scope_write=["src/app.py"])])
        (root / "new.txt").write_text("new\n")
        result = json.loads(self.run_check(root, "--json").stdout)
        self.assertIn("new.txt", result["changed"])

        root = make_project([task(scope_write=["src/app.py"])])
        (root / "README.md").unlink()
        result = json.loads(self.run_check(root, "--json").stdout)
        self.assertIn("README.md", result["changed"])

        root = make_project([task(scope_write=["src/app.py"])])
        (root / "staged.txt").write_text("s\n")
        git(root, "add", "staged.txt")
        result = json.loads(self.run_check(root, "--json").stdout)
        self.assertIn("staged.txt", result["changed"])

        root = make_project([task(scope_write=["src/moved.py"])])
        git(root, "mv", "src/app.py", "src/moved.py")
        result = json.loads(self.run_check(root, "--json").stdout)
        self.assertIn("src/moved.py", result["changed"])
        self.assertIn("src/app.py", result["changed"])
        self.assertFalse(result["ok"], "the old path of a rename is outside the scope")

    def test_path_with_spaces(self):
        root = make_project([task(scope_write=["docs/"])])
        (root / "docs").mkdir()
        (root / "docs" / "my notes.md").write_text("n\n")
        result = self.run_check(root)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_no_or_several_running_tasks(self):
        root = make_project([task(status="pending")])
        self.assertEqual(self.run_check(root).returncode, 2)
        root = make_project([task("M01"), task("M02")])
        result = self.run_check(root)
        self.assertEqual(result.returncode, 2)
        self.assertIn("several", result.stderr)
        self.assertEqual(self.run_check(root, "--task", "M02").returncode, 0)

    def test_environment_errors(self):
        root = make_project([task()])
        (root / "board.json").write_text("{not json")
        self.assertEqual(self.run_check(root).returncode, 2)
        root = make_project([task()])
        import shutil
        shutil.rmtree(root / ".git")
        self.assertEqual(self.run_check(root).returncode, 2)

    def test_evidence_folder_is_always_allowed(self):
        root = make_project([task()])
        (root / "reviews" / "evidence").mkdir(parents=True)
        (root / "reviews" / "evidence" / "M01-tests.log").write_text("ok\n")
        self.assertEqual(self.run_check(root).returncode, 0)

    def test_board_files_need_allow_board(self):
        root = make_project([task()])
        board = json.loads((root / "board.json").read_text())
        board["stage"] = 2
        (root / "board.json").write_text(json.dumps(board))
        result = self.run_check(root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("lead-owned", result.stdout)
        self.assertEqual(self.run_check(root, "--allow-board").returncode, 0)

    def test_no_changes(self):
        root = make_project([task()])
        result = self.run_check(root)
        self.assertEqual(result.returncode, 0)
        self.assertIn("no changes", result.stdout)


if __name__ == "__main__":
    unittest.main()
