"""core.scope: the guard decision, the stop check and their messages."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.errors import PolierError
from core.scope import changed_files, check_stop, check_write, scope_check, stop_message, write_denial

from .fixtures import git, project, set_board, task

CASES = json.loads((Path(__file__).with_name("write_cases.json")).read_text(encoding="utf-8"))


class WriteCases(unittest.TestCase):
    """The table the DSH adapter's JS mirror is tested against as well."""

    def test_shared_cases(self):
        for case in CASES["cases"]:
            with self.subTest(case["name"]):
                tasks = [CASES["tasks"][k] for k in case["tasks"]]
                decision = check_write(case["path"], tasks, role=case.get("role", "worker"))
                self.assertEqual(decision.ok, case["ok"], decision)
                if not case["ok"]:
                    self.assertEqual(decision.code, case["code"])


class CheckWrite(unittest.TestCase):
    def test_absolute_and_cwd_relative_paths(self):
        root = Path(tempfile.mkdtemp())
        t = task()
        self.assertTrue(check_write(str(root / "src" / "app.py"), t, root=root).ok)
        self.assertTrue(check_write("app.py", t, root=root, cwd=root / "src").ok)
        decision = check_write("../README.md", t, root=root, cwd=root / "src")
        self.assertEqual((decision.ok, decision.path), (False, "README.md"))
        self.assertEqual(check_write("/elsewhere/x", t, root=root).code, "outside-project")

    def test_single_task_dict(self):
        self.assertTrue(check_write("src/app.py", task()).ok)

    def test_denial_messages(self):
        tasks = [task("M01"), task("M02", scope_write=["README.md", "src/app.py"])]
        decision = check_write("docs/x.md", tasks)
        self.assertEqual(
            write_denial(decision, tasks),
            "Polier: write to docs/x.md blocked, the path is outside the write scope of M01, M02. "
            "Allowed: src/app.py, tests/, README.md. Do not try another way to write it. "
            "If the change is needed, stop and report it under open_questions.")
        reviewer = check_write("src/app.py", tasks, role="reviewer")
        self.assertIn("a reviewer session writes only under reviews/", write_denial(reviewer, tasks, "reviewer"))


class StopCheck(unittest.TestCase):
    def test_check_stop_without_git(self):
        result = check_stop(["src/app.py", "README.md", "board.json", "reviews/evidence/a.log"], task())
        self.assertFalse(result["ok"])
        self.assertEqual(result["violations"], [
            {"path": "README.md", "reason": "outside scope"},
            {"path": "board.json", "reason": "lead-owned (board, status or brief)"},
        ])
        self.assertTrue(check_stop(["board.json"], task(), allow_board=True)["ok"])

    def test_forbidden_wins_over_evidence(self):
        t = task(scope_write=["src/"], scope_write_forbidden=["reviews/"])
        self.assertEqual(check_stop(["reviews/evidence/a.log"], t)["violations"][0]["reason"], "forbidden")

    def test_outside_project(self):
        self.assertEqual(check_stop(["../x"], task())["violations"][0]["reason"], "outside the project")

    def test_changed_files_and_scope_check(self):
        root = project([task()])
        self.assertEqual(changed_files(root), [])
        (root / "README.md").write_text("changed\n")
        (root / "new.txt").write_text("n\n")
        git(root, "mv", "src/app.py", "src/moved.py")
        self.assertEqual(sorted(changed_files(root)), ["README.md", "new.txt", "src/app.py", "src/moved.py"])
        result = scope_check(root)
        self.assertEqual(result["task"], "M01")
        self.assertFalse(result["ok"])

    def test_project_in_a_subfolder_of_the_repo(self):
        root = project([task()])
        sub = root / "app"
        sub.mkdir()
        (sub / "board.json").write_text(json.dumps({"tasks": [task()]}))
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "sub")
        (root / "README.md").write_text("x\n")
        (sub / "src").mkdir()
        (sub / "src" / "app.py").write_text("y\n")
        self.assertEqual(sorted(changed_files(sub)), ["../README.md", "src/app.py"])

    def test_scope_check_errors(self):
        root = project([task()], repo=False)
        with self.assertRaisesRegex(PolierError, "not a git repository"):
            scope_check(root)
        root = project([task("M01", "pending")])
        with self.assertRaises(PolierError):
            scope_check(root)
        set_board(root, tasks="nope")
        with self.assertRaisesRegex(PolierError, "no task list"):
            scope_check(root)

    def test_stop_message(self):
        text = stop_message(task(), [{"path": "README.md", "reason": "outside scope"}])
        self.assertTrue(text.startswith("Polier: the working tree has changes outside the scope of M01.\n"))
        self.assertIn("- README.md: outside scope\nAllowed: src/app.py, tests/.", text)


if __name__ == "__main__":
    unittest.main()


import os  # noqa: E402
import platform  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402

from core import claims as claims_module  # noqa: E402
from core.board import load_board  # noqa: E402
from core.claims import take  # noqa: E402

WORKTREE_TOOL = Path(__file__).resolve().parents[2] / "tools" / "worktree.py"


def run_worktree(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(WORKTREE_TOOL), *args],
                          capture_output=True, text=True, check=False)


def repo_board(root: Path, **changes) -> dict:
    set_board(root, **changes)
    return load_board(root)


class WorktreeRule(unittest.TestCase):
    """PL-05: a worker bound to a task worktree writes only in that worktree."""

    def setUp(self):
        self.root = project([task(worktree=str(Path(tempfile.mkdtemp()) / "repo-M01"))])
        self.tree = self.root / ".." / "repo-M01"
        self.tree = str(self.tree)
        set_board(self.root, profile="M", schema_version="1.0")
        self.board = load_board(self.root)
        self.task = self.board["tasks"][0]

    def decide(self, rel: str, board=None, root=None):
        return check_write(rel, [self.task], root=root or self.root, board=board or self.board)

    def test_required_by_profile_denies_the_main_checkout(self):
        decision = self.decide("src/app.py")
        self.assertFalse(decision.ok)
        self.assertEqual(decision.code, "worktree")
        self.assertEqual(decision.reason, f"work in {self.task['worktree']}")
        self.assertIn(f"work in {self.task['worktree']}", write_denial(decision, [self.task]))
        self.assertFalse(decision.path == "")

    def test_evidence_stays_writable_in_the_main_checkout(self):
        self.assertTrue(self.decide("reviews/evidence/M01-tests.log").ok)

    def test_no_board_or_root_keeps_the_old_behaviour(self):
        self.assertTrue(self.decide("src/app.py", board=None))
        self.assertTrue(check_write("src/app.py", [self.task]))
        self.assertTrue(check_write("src/app.py", [self.task], root=self.root))

    def test_profile_s_defaults_to_off(self):
        root = project([task(worktree="/somewhere/repo-M01")])
        board = load_board(root)
        self.assertTrue(check_write("src/app.py", [board["tasks"][0]], root=root, board=board).ok)

    def test_explicit_modes(self):
        for mode in ("off", "recommended"):
            with self.subTest(mode):
                set_board(self.root, worktrees=mode)
                board = load_board(self.root)
                self.assertTrue(self.decide("src/app.py", board=board).ok)
        set_board(self.root, worktrees="required")
        board = load_board(self.root)
        self.assertEqual(self.decide("src/app.py", board=board).code, "worktree")

    def test_required_on_profile_s_denies(self):
        root = project([task(worktree="/somewhere/repo-M01")])
        board = repo_board(root, worktrees="required")
        self.assertEqual(check_write("src/app.py", [board["tasks"][0]], root=root, board=board).code,
                         "worktree")

    def test_inside_the_worktree_nothing_is_denied(self):
        linked = self.root.parent / f"{self.root.name}-linked"
        git(self.root, "worktree", "add", str(linked), "-b", "task/M01")
        try:
            decision = check_write("src/app.py", [self.task], root=linked, board=self.board)
            self.assertTrue(decision.ok, decision)
        finally:
            subprocess.run(["git", "-C", str(self.root), "worktree", "remove", "--force", str(linked)],
                           capture_output=True, check=False)

    def test_a_task_without_worktree_is_not_denied(self):
        root = project([task()])
        board = repo_board(root, profile="M")
        self.assertTrue(check_write("src/app.py", [board["tasks"][0]], root=root, board=board).ok)

    @unittest.skipUnless(platform.system() in ("Darwin", "Windows"),
                         "case-insensitive file systems only")
    def test_board_json_in_another_case_is_lead_owned(self):
        root = project([task()])
        board = load_board(root)
        decision = check_write("Board.json", [board["tasks"][0]], root=root, board=board)
        self.assertEqual(decision.code, "lead-owned")


class ForeignChanges(unittest.TestCase):
    """PL-05: changes made under another live claim's scope are not this task's violations."""

    def setUp(self):
        self.root = project([
            task("M01"),
            task("M02", "pending", scope_write=["docs/"]),
        ])
        self.board = load_board(self.root)
        self.m01 = self.board["tasks"][0]
        take(self.root, "M02", harness="dsh", session="agent-other")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "x.md").write_text("foreign\n")

    def test_foreign_change_is_reported_separately(self):
        result = check_stop(changed_files(self.root), self.m01, root=self.root)
        self.assertTrue(result["ok"])
        self.assertEqual(result["violations"], [])
        self.assertEqual(result["foreign"], [
            {"path": "docs/x.md", "task": "M02", "harness": "dsh"},
        ])

    def test_files_in_nobody_scope_stay_violations(self):
        (self.root / "README.md").write_text("changed\n")
        result = check_stop(changed_files(self.root), self.m01, root=self.root)
        self.assertFalse(result["ok"])
        self.assertEqual([v["path"] for v in result["violations"]], ["README.md"])
        self.assertEqual(len(result["foreign"]), 1)

    def test_without_root_there_are_no_foreign_changes(self):
        result = check_stop(changed_files(self.root), self.m01)
        self.assertFalse(result["ok"])
        self.assertEqual([v["path"] for v in result["violations"]], ["docs/x.md"])
        self.assertEqual(result["foreign"], [])

    def test_a_stale_claim_does_not_make_a_change_foreign(self):
        path = claims_module.claim_dir(self.root) / "M02.json"
        claim = claims_module.read_claim(self.root, "M02")
        claim["heartbeat"] = claim["started"] = "2020-01-01T00:00:00+00:00"
        path.write_text(json.dumps(claim), encoding="utf-8")
        result = check_stop(changed_files(self.root), self.m01, root=self.root)
        self.assertFalse(result["ok"])
        self.assertEqual([v["path"] for v in result["violations"]], ["docs/x.md"])
        self.assertEqual(result["foreign"], [])

    def test_scope_check_passes_the_root_through(self):
        result = scope_check(self.root)
        self.assertEqual(result["task"], "M01")
        self.assertEqual(result["foreign"][0]["task"], "M02")


class Worktrees(unittest.TestCase):
    """PL-05: tools/worktree.py start and finish."""

    def test_start_creates_worktree_branch_slot_and_claim_then_finish_removes_them(self):
        root = project([task()])
        target = root.parent / f"{root.name}-M01"
        started = run_worktree("start", "M01", "--root", str(root), "--base", "main",
                               "--session", "test-session")
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertEqual(started.stdout.strip(), str(target))
        self.assertTrue(target.is_dir())
        board = json.loads((root / "board.json").read_text())
        stored = board["tasks"][0]["worktree"]
        self.assertEqual(stored, os.path.relpath(str(target), str(root)).replace(os.sep, "/"))
        claim = claims_module.read_claim(root, "M01")
        self.assertEqual((claim["task"], claim["harness"], claim["session"]),
                         ("M01", "cli", "test-session"))
        self.assertEqual(claim["worktree"], str(target))

        # Uncommitted changes: refuse and change nothing.
        (target / "README.md").write_text("dirty\n")
        refused = run_worktree("finish", "M01", "--root", str(root))
        self.assertEqual(refused.returncode, 1)
        self.assertIn("uncommitted changes", refused.stderr)
        self.assertTrue(target.is_dir())
        self.assertIsNotNone(claims_module.read_claim(root, "M01"))
        self.assertEqual(json.loads((root / "board.json").read_text())["tasks"][0]["worktree"], stored)

        git(target, "add", "README.md")
        git(target, "commit", "-q", "-m", "task work")
        finished = run_worktree("finish", "M01", "--root", str(root))
        self.assertEqual(finished.returncode, 0, finished.stderr)
        self.assertFalse(target.exists())
        self.assertIsNone(claims_module.read_claim(root, "M01"))
        self.assertIsNone(json.loads((root / "board.json").read_text())["tasks"][0]["worktree"])

    def test_start_refuses_a_task_that_already_has_a_worktree(self):
        root = project([task()])
        self.assertEqual(run_worktree("start", "M01", "--root", str(root)).returncode, 0)
        second = run_worktree("start", "M01", "--root", str(root))
        self.assertEqual(second.returncode, 1)
        self.assertIn("already has a worktree", second.stderr)
        self.assertEqual(run_worktree("finish", "M01", "--root", str(root)).returncode, 0)

    def test_start_rolls_back_when_another_session_holds_the_claim(self):
        root = project([task()])
        take(root, "M01", harness="dsh", session="agent-other")
        target = root.parent / f"{root.name}-M01"
        result = run_worktree("start", "M01", "--root", str(root))
        self.assertEqual(result.returncode, 1)
        self.assertIn("agent-other", result.stderr)
        self.assertFalse(target.exists())
        self.assertEqual(claims_module.read_claim(root, "M01")["session"], "agent-other")
        branch = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "--quiet",
                                 "refs/heads/task/M01"], capture_output=True, text=True, check=False)
        self.assertNotEqual(branch.returncode, 0)

    def test_finish_refuses_a_task_without_worktree(self):
        root = project([task()])
        result = run_worktree("finish", "M01", "--root", str(root))
        self.assertEqual(result.returncode, 1)
        self.assertIn("no worktree", result.stderr)

    def test_environment_errors(self):
        bare = project([task()], repo=False)
        self.assertEqual(run_worktree("start", "M01", "--root", str(bare)).returncode, 2)
        root = project([task()])
        unknown = run_worktree("start", "M99", "--root", str(root))
        self.assertEqual(unknown.returncode, 2)
        self.assertIn("not on the board", unknown.stderr)


class WorktreeModeDefault(unittest.TestCase):
    """PL-05 migration: a 0.9 M/L board defaults to recommended, a 1.0 board to required."""

    def test_defaults(self):
        from core.scope import worktree_mode
        self.assertEqual(worktree_mode({"profile": "S"}), "off")
        self.assertEqual(worktree_mode({"profile": "M"}), "recommended")
        self.assertEqual(worktree_mode({"profile": "L"}), "recommended")
        self.assertEqual(worktree_mode({"profile": "M", "schema_version": "1.0"}), "required")
        self.assertEqual(worktree_mode({"profile": "L", "schema_version": "1.0"}), "required")
        self.assertEqual(worktree_mode({"profile": "M", "worktrees": "off"}), "off")
