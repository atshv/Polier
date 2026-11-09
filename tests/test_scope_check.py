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

    def test_briefs_need_allow_board(self):
        root = make_project([task()])
        (root / "tasks").mkdir()
        (root / "tasks" / "M01.md").write_text("# M01 — changed\n")
        result = self.run_check(root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("lead-owned", result.stdout)
        self.assertEqual(self.run_check(root, "--allow-board").returncode, 0)

    def test_board_changes_are_records_not_violations(self):
        root = make_project([task()])
        board = json.loads((root / "board.json").read_text())
        board["stage"] = 2
        (root / "board.json").write_text(json.dumps(board))
        result = self.run_check(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("RECORDS", result.stdout)

    def test_no_changes(self):
        root = make_project([task()])
        result = self.run_check(root)
        self.assertEqual(result.returncode, 0)
        self.assertIn("no changes", result.stdout)

class Baseline(unittest.TestCase):
    """What was changed before the task was bound, and the tools' records, are not the builder's."""

    def test_records_and_baseline_do_not_count(self):
        root = make_project([task(scope_write=["src/app.py"])])
        (root / "README.md").write_text("lead edit before the task\n", encoding="utf-8")
        (root / "runs").mkdir()
        (root / "runs" / "M01.json").write_text("{}", encoding="utf-8")
        self.assertEqual(run_tool("scope_check.py", str(root), "--task", "M01", "--snapshot").returncode, 0)
        (root / "STATUS.md").write_text("regenerated\n", encoding="utf-8")
        (root / "src" / "app.py").write_text("x = 2\n", encoding="utf-8")
        result = run_tool("scope_check.py", str(root), "--task", "M01", "--json")
        data = json.loads(result.stdout)
        self.assertTrue(data["ok"], data)
        self.assertIn("STATUS.md", data["records"])
        self.assertIn("README.md", data["baseline"])

    def test_a_baseline_file_changed_again_counts(self):
        root = make_project([task(scope_write=["src/app.py"])])
        (root / "README.md").write_text("before\n", encoding="utf-8")
        run_tool("scope_check.py", str(root), "--task", "M01", "--snapshot")
        (root / "README.md").write_text("changed by the builder\n", encoding="utf-8")
        data = json.loads(run_tool("scope_check.py", str(root), "--task", "M01", "--json").stdout)
        self.assertFalse(data["ok"])
        self.assertEqual([v["path"] for v in data["violations"]], ["README.md"])


if __name__ == "__main__":
    unittest.main()


class OneOneScopeCodes(unittest.TestCase):
    """Codes of core/tests/write_cases.json: runs/ is
    lead-owned and a reviewer may not write the approval ledger."""

    def run_check(self, root, *args):
        return run_tool("scope_check.py", str(root), *args)

    def test_run_records_do_not_count_against_the_worker(self):
        root = make_project([task()])
        (root / "runs").mkdir()
        (root / "runs" / "M01.json").write_text("{}\n", encoding="utf-8")
        result = self.run_check(root, "--json")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["records"], ["runs/M01.json"])

    def test_reviewer_may_not_write_the_approval_ledger(self):
        from core.scope import check_write
        decision = check_write("reviews/approvals/AP-001.json", [task()], role="reviewer")
        self.assertEqual((decision.ok, decision.code), (False, "approvals"))
        self.assertIn("approval ledger", decision.reason)

    def test_reviewer_still_writes_review_material(self):
        from core.scope import check_write
        self.assertTrue(check_write("reviews/M01.md", [task()], role="reviewer").ok)

    def test_worker_still_writes_gate_evidence(self):
        from core.scope import check_write
        self.assertTrue(check_write("reviews/evidence/x.json", [task()]).ok)
