"""Rules of tools/check.py: stage gates (PL-08), budgets (PL-09), packages (PL-06), versions (PL-13)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers import git, task

import check  # noqa: E402  (tools/ is on sys.path via helpers)

from core.board import board_errors, ready_tasks, stage_report  # noqa: E402


def stage(sid: str, **extra) -> dict:
    data = {"id": sid, "title": f"Stage {sid}", "exit_gates": [], "depends_on": []}
    data.update(extra)
    return data


def board(stages: list, tasks: list, **extra) -> dict:
    data = {
        "project": "t", "profile": "M", "base_branch": "main", "schema_version": "1.0",
        "stages": stages, "tasks": tasks,
    }
    data.update(extra)
    return data


def temp_root() -> Path:
    return Path(tempfile.mkdtemp(prefix="pl-rules-")).resolve()


class Stages(unittest.TestCase):
    def fixture(self, decision: str = "pending", s2_complete: bool = False) -> dict:
        s1_task = task("T-01", status="done", stage="s1", gates=["tests"],
                       evidence=["reviews/evidence/T-01-tests-1.json"])
        s2_task = task("T-02", status="done" if s2_complete else "pending", stage="s2",
                       depends_on=["T-01"], gates=["e2e"],
                       evidence=["reviews/evidence/T-02-e2e-1.json"] if s2_complete else [])
        s3_task = task("T-03", status="pending", stage="s3", depends_on=["T-01"])
        return board(
            [stage("s1", exit_gates=["tests"]),
             stage("s2", depends_on=["s1"], exit_gates=["e2e"], owner_decision=decision),
             stage("s3", depends_on=["s2"])],
            [s1_task, s2_task, s3_task],
        )

    def test_pending_owner_decision_keeps_later_stage_unready(self):
        data = self.fixture("pending")
        self.assertEqual(board_errors(data), [])
        ready = [t["id"] for t in ready_tasks(data)]
        self.assertEqual(ready, ["T-02"], ready)
        report = {r["id"]: r for r in stage_report(data)}
        self.assertFalse(report["s2"]["complete"])
        self.assertTrue(report["s2"]["owner_pending"])
        self.assertEqual(report["s3"]["incomplete_deps"], ["s2"])

    def test_continue_plus_exit_gates_makes_later_stage_ready(self):
        data = self.fixture("continue", s2_complete=True)
        report = {r["id"]: r for r in stage_report(data)}
        self.assertTrue(report["s2"]["complete"], report["s2"])
        self.assertEqual(report["s3"]["incomplete_deps"], [])
        ready = [t["id"] for t in ready_tasks(data)]
        self.assertIn("T-03", ready, ready)

    def test_stopped_stage_blocks_dependants_and_check_errors(self):
        data = self.fixture("stop", s2_complete=True)
        report = {r["id"]: r for r in stage_report(data)}
        self.assertTrue(report["s2"]["stopped"])
        self.assertFalse(report["s3"]["complete"])
        data["tasks"][2]["status"] = "in_progress"  # work in the blocked stage
        data["tasks"][1]["status"] = "done"
        errors: list[str] = []
        warnings: list[str] = []
        check.check_stages(temp_root(), data, errors, warnings)
        self.assertTrue(any("T-03" in error and "s3" in error for error in errors), errors)

    def test_record_file_is_verified_when_root_is_given(self):
        """With a root the stage gate needs a real passing record, not just an evidence string."""
        data = self.fixture("continue", s2_complete=True)
        data["tasks"][1]["status"] = "done"
        root = temp_root()
        (root / "board.json").write_text(json.dumps(data), encoding="utf-8")
        self.assertFalse({r["id"]: r for r in stage_report(data, root)}["s2"]["complete"])
        folder = root / "reviews" / "evidence"
        folder.mkdir(parents=True)
        for task_id, gate_name in (("T-01", "tests"), ("T-02", "e2e")):
            (folder / f"{task_id}-{gate_name}-1.json").write_text(json.dumps(
                {"task": task_id, "gate": gate_name, "exit_code": 0, "result": "pass",
                 "log": f"{task_id}-{gate_name}-1.log"}), encoding="utf-8")
        self.assertTrue({r["id"]: r for r in stage_report(data, root)}["s1"]["complete"])
        self.assertTrue({r["id"]: r for r in stage_report(data, root)}["s2"]["complete"])
        (folder / "T-02-e2e-1.json").unlink()  # only a broken record now: not evidence
        (folder / "T-02-e2e-2.json").write_text(json.dumps(
            {"task": "T-02", "gate": "e2e", "exit_code": 124, "result": "timeout"}),
            encoding="utf-8")
        self.assertFalse({r["id"]: r for r in stage_report(data, root)}["s2"]["complete"])

    def test_stage_without_exit_gates_warns(self):
        data = board([stage("s1")], [task("T-01", stage="s1")])
        errors: list[str] = []
        warnings: list[str] = []
        check.check_stages(temp_root(), data, errors, warnings)
        self.assertTrue(any("no exit_gates" in warning for warning in warnings), warnings)


class Budgets(unittest.TestCase):
    def test_profile_defaults(self):
        for profile, status in (("S", 300), ("M", 500), ("L", 900)):
            limits, overrides = check.budget_limits({"profile": profile})
            self.assertEqual(limits["status"], status)
            self.assertEqual(overrides, [])
        self.assertEqual(check.budget_limits({"profile": "L"})[0]["architecture"], 800)

    def test_l_project_may_have_a_longer_status(self):
        limits, _ = check.budget_limits({"profile": "L"})
        self.assertLessEqual(850, limits["status"])

    def test_override_needs_a_reason(self):
        data = {"project": "t", "profile": "L", "base_branch": "main", "schema_version": "1.0",
                "budgets": {"status": {"limit": 850}},
                "stages": [], "tasks": [task("M01", stage=1)]}
        self.assertIn("without a reason", "\n".join(board_errors(data)))
        data["budgets"]["status"]["reason"] = "32 tasks in stage 2"
        self.assertEqual(board_errors(data), [])
        limits, overrides = check.budget_limits(data)
        self.assertEqual(limits["status"], 850)
        self.assertTrue(any("reason: 32 tasks in stage 2" in line for line in overrides), overrides)


class Packages(unittest.TestCase):
    def make(self, board_data: dict) -> Path:
        root = temp_root()
        (root / "board.json").write_text(json.dumps(board_data), encoding="utf-8")
        (root / "docs").mkdir()
        (root / "docs/module-map.md").write_text("packages/core\n", encoding="utf-8")
        return root

    def test_l_needs_packages(self):
        data = {"project": "t", "profile": "L", "base_branch": "main", "schema_version": "1.0",
                "tasks": [task("T-01", stage=1)]}
        errors: list[str] = []
        check.check_packages(self.make(data), data, errors, [])
        self.assertTrue(any("packages[]" in error for error in errors), errors)

    def test_task_scope_outside_its_package_is_an_error(self):
        data = {"project": "t", "profile": "M", "base_branch": "main", "schema_version": "1.0",
                "packages": [{"path": "packages/core", "kind": "package"}],
                "tasks": [task("T-01", stage=1, package="packages/core",
                               scope_write=["packages/core/a.py", "docs/api.md"])]}
        root = self.make(data)
        (root / "packages/core").mkdir(parents=True)
        (root / "packages/core/ARCHITECTURE.md").write_text("x " * 200, encoding="utf-8")
        errors: list[str] = []
        check.check_packages(root, data, errors, [])
        self.assertTrue(any("docs/api.md" in error and "outside its package" in error for error in errors), errors)

    def test_contract_path_is_allowed(self):
        data = {"project": "t", "profile": "M", "base_branch": "main", "schema_version": "1.0",
                "packages": [{"path": "packages/core", "kind": "package"}],
                "contracts": [{"name": "api", "path": "contracts/api", "version": "1.0.0"}],
                "tasks": [task("T-01", stage=1, package="packages/core",
                               scope_write=["packages/core/a.py", "contracts/api/schema.json"])]}
        root = self.make(data)
        (root / "packages/core").mkdir(parents=True)
        (root / "packages/core/ARCHITECTURE.md").write_text("x " * 200, encoding="utf-8")
        errors: list[str] = []
        check.check_packages(root, data, errors, [])
        self.assertEqual(errors, [])

    def test_package_created_by_a_named_task_is_accepted(self):
        data = {"project": "t", "profile": "M", "base_branch": "main", "schema_version": "1.0",
                "packages": [{"path": "packages/core", "kind": "package"}],
                "tasks": [task("T-01", status="pending", stage=1,
                               scope_write=["packages/core/app.py"])]}
        root = self.make(data)
        errors: list[str] = []
        check.check_packages(root, data, errors, [])
        self.assertEqual(errors, [])


class Versions(unittest.TestCase):
    def test_manifest_dependency_missing_in_versions_md_warns(self):
        root = temp_root()
        (root / "package.json").write_text(json.dumps(
            {"dependencies": {"react": "^19.0.0", "pinned-lib": "1.2.3"}}), encoding="utf-8")
        (root / "docs").mkdir()
        (root / "docs/versions.md").write_text("| react | 19.0.0 | ... |\n", encoding="utf-8")
        warnings: list[str] = []
        check.check_versions(root, {"profile": "L"}, warnings)
        self.assertTrue(any("pinned-lib" in warning for warning in warnings), warnings)
        self.assertFalse(any("react" in warning for warning in warnings), warnings)

    def test_not_checked_below_profile_l(self):
        warnings: list[str] = []
        check.check_versions(temp_root(), {"profile": "M"}, warnings)
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
