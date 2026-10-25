"""Release gate (PL-10): clean tagged HEAD on the base branch, released stages done."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core.tests.fixtures import git, project, task

TOOLS = Path(__file__).resolve().parents[2] / "tools"

STAGES = [{
    "id": "foundation", "title": "Foundation", "goal": "Scaffold the repository",
    "exit_criteria": ["CI green"], "exit_gates": ["tests"],
    "owner_decision": "continue", "depends_on": [],
}]


def release_check():
    spec = importlib.util.spec_from_file_location("pl_release_check", TOOLS / "release_check.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def cli(root, *args):
    return subprocess.run([sys.executable, str(TOOLS / "release_check.py"), str(root), *args],
                          capture_output=True, text=True, check=False)


def head(root) -> str:
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


def commit(root, message: str = "board: stages") -> None:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)


def write_board(root: Path, board: dict) -> None:
    (root / "board.json").write_text(json.dumps(board), encoding="utf-8")


def released_board(status: str = "pending", decision: str = "continue",
                   gate: str = "tests") -> dict:
    stage = dict(STAGES[0], owner_decision=decision, exit_gates=[gate])
    tasks = [
        task("M01", status="done", stage="foundation"),
        task("M02", status=status, stage="foundation", depends_on=["M01"]),
    ]
    return {"project": "t", "profile": "S", "base_branch": "main",
            "schema_version": "1.0", "stages": [stage], "tasks": tasks}


def passing_record(root: Path, gate: str = "tests", exit_code: int = 0,
                   result: str | None = None) -> None:
    folder = root / "reviews" / "evidence"
    folder.mkdir(parents=True, exist_ok=True)
    record = {"task": "M01", "gate": gate, "exit_code": exit_code}
    if result is not None:
        record["result"] = result
    (folder / f"M01-{gate}-20260101T000000Z.json").write_text(json.dumps(record), encoding="utf-8")


class CleanTagged(unittest.TestCase):
    def test_clean_tagged_head_on_main_is_ok(self):
        root = project([task(status="pending")])
        git(root, "tag", "v1.0.0")
        result = release_check().check(root)

        self.assertEqual(
            set(result), {"ok", "errors", "warnings", "tag", "commit", "base_branch"})
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["tag"], "v1.0.0")
        self.assertEqual(result["commit"], head(root))
        self.assertEqual(result["base_branch"], "main")

        run = cli(root)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("RELEASE OK", run.stdout)

    def test_cli_json(self):
        root = project([task(status="pending")])
        git(root, "tag", "v1.0.0")
        run = cli(root, "--json")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["tag"], "v1.0.0")


class DirtyTree(unittest.TestCase):
    def test_dirty_tree_fails_and_lists_files(self):
        root = project([task()])
        git(root, "tag", "v1.0.0")
        (root / "README.md").write_text("changed\n", encoding="utf-8")
        (root / "notes.txt").write_text("new\n", encoding="utf-8")

        result = release_check().check(root)
        self.assertFalse(result["ok"])
        message = "\n".join(result["errors"])
        self.assertIn("dirty", message)
        self.assertIn("README.md", message)
        self.assertIn("notes.txt", message)

        run = cli(root)
        self.assertEqual(run.returncode, 1)
        self.assertIn("README.md", run.stdout)


class Untagged(unittest.TestCase):
    def test_untagged_is_an_error_unless_allowed(self):
        root = project([task()])
        module = release_check()

        result = module.check(root)
        self.assertFalse(result["ok"])
        self.assertIn("not tagged", "\n".join(result["errors"]))
        self.assertIsNone(result["tag"])
        self.assertEqual(cli(root).returncode, 1)

        allowed = module.check(root, allow_untagged=True)
        self.assertTrue(allowed["ok"], allowed)
        self.assertIsNone(allowed["tag"])
        self.assertIn("not tagged", "\n".join(allowed["warnings"]))
        self.assertEqual(cli(root, "--allow-untagged").returncode, 0)


class TagOnBase(unittest.TestCase):
    def test_tag_outside_the_base_branch_fails(self):
        root = project([task()])
        git(root, "checkout", "-q", "-b", "feature")
        (root / "feature.txt").write_text("f\n", encoding="utf-8")
        commit(root, "feat: work")
        git(root, "tag", "v1.0.0")

        result = release_check().check(root)
        self.assertFalse(result["ok"])
        message = "\n".join(result["errors"])
        self.assertIn("not an ancestor", message)
        self.assertIn("main", message)

        # The same commit is fine when the base branch is the branch that has it,
        # both through the function argument and through --base.
        self.assertTrue(release_check().check(root, base_branch="feature")["ok"])
        self.assertEqual(cli(root, "--base", "feature").returncode, 0)


class ReleasedStages(unittest.TestCase):
    def _repo(self, board: dict, record: dict | None = None) -> Path:
        root = project([task("M01", status="done", stage="foundation"),
                        task("M02", status="pending", stage="foundation")])
        write_board(root, board)
        if record is not None:
            passing_record(root, **record)
        commit(root)
        git(root, "tag", "v1.0.0")
        return root

    def test_released_stage_with_pending_task_fails(self):
        root = self._repo(released_board(), {"gate": "tests"})
        result = release_check().check(root)
        self.assertFalse(result["ok"], result)
        message = "\n".join(result["errors"])
        self.assertIn("released", message)
        self.assertIn("foundation", message)
        self.assertIn("M02", message)

        run = cli(root, "--json")
        self.assertEqual(run.returncode, 1)
        self.assertIn("M02", "\n".join(json.loads(run.stdout)["errors"]))

    def test_stage_with_pending_owner_decision_is_not_released(self):
        root = self._repo(released_board(decision="pending"), {"gate": "tests"})
        self.assertTrue(release_check().check(root)["ok"])

    def test_stage_without_a_passing_exit_gate_is_not_released(self):
        root = self._repo(released_board(gate="e2e"), {"gate": "tests"})
        self.assertTrue(release_check().check(root)["ok"])

    def test_failed_or_infra_record_does_not_release_a_stage(self):
        for record in ({"gate": "tests", "exit_code": 1},
                       {"gate": "tests", "result": "infra"}):
            root = self._repo(released_board(), record)
            self.assertTrue(release_check().check(root)["ok"], record)

    def test_board_without_stages_skips_the_rule(self):
        root = project([task("M01", status="done"), task("M02", status="pending")])
        git(root, "tag", "v1.0.0")
        self.assertTrue(release_check().check(root)["ok"])

    def test_board_argument_is_used_instead_of_disk(self):
        root = project([task("M01", status="done", stage="foundation"),
                        task("M02", status="pending", stage="foundation")])
        passing_record(root, gate="tests")
        commit(root)
        git(root, "tag", "v1.0.0")
        module = release_check()
        # On disk the repo has no stages; the passed board has a released stage.
        self.assertTrue(module.check(root)["ok"])
        self.assertFalse(module.check(root, board=released_board())["ok"])


class Environment(unittest.TestCase):
    def test_no_git_repository_exits_2(self):
        root = Path(tempfile.mkdtemp(prefix="pl-release-")).resolve()
        write_board(root, released_board())
        run = cli(root)
        self.assertEqual(run.returncode, 2)
        self.assertIn("not a git repository", run.stderr)
        # The function never raises; it reports the environment problem.
        result = release_check().check(root)
        self.assertFalse(result["ok"])
        self.assertTrue(result["errors"])

    def test_missing_board_only_warns(self):
        root = project([task()])
        (root / "board.json").unlink()
        commit(root, "chore: drop board")
        git(root, "tag", "v1.0.0")
        result = release_check().check(root)
        self.assertTrue(result["ok"], result)
        self.assertIn("board.json", "\n".join(result["warnings"]))


if __name__ == "__main__":
    unittest.main()
