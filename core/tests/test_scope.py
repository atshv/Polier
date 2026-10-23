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
