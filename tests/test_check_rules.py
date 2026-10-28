"""Rules of tools/check.py: stage gates (PL-08), budgets (PL-09), packages (PL-06), versions (PL-13)
and the 1.1 orchestration checks (policy, audit, approvals, run records, scopes, dispatch, docs)."""
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


class OrchestrationChecks(unittest.TestCase):
    """1.1: policy, audit, approvals, run records, scopes, dispatch and docs."""

    def project(self, policy=None, *, agents=True, readme=True, orchestration=True,
                agents_text=None, readme_text=None) -> Path:
        root = temp_root()
        (root / "policy.json").write_text(
            json.dumps({"version": 1} if policy is None else policy), encoding="utf-8")
        if agents:
            (root / "AGENTS.md").write_text(
                agents_text or "State changes with tools/state.py; never edit runs/. "
                               "policy.json is committed.\n", encoding="utf-8")
        if readme:
            (root / "README.md").write_text(
                readme_text or "Limits live in policy.json; runs/ holds the records.\n",
                encoding="utf-8")
        if orchestration:
            (root / "docs").mkdir()
            (root / "docs/orchestration.md").write_text("# Orchestration\n", encoding="utf-8")
        return root

    def run_checks(self, root: Path, board_data: dict) -> tuple[list, list]:
        errors: list[str] = []
        warnings: list[str] = []
        check.check_orchestration(root, board_data, errors, warnings)
        return errors, warnings

    def board(self, *tasks: dict, **extra) -> dict:
        data = {"project": "t", "profile": "S", "base_branch": "main", "tasks": list(tasks)}
        data.update(extra)
        return data

    def write_json(self, root: Path, rel: str, data) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    # -- policy ------------------------------------------------------------

    def test_a_project_without_a_policy_only_warns(self):
        errors, warnings = self.run_checks(temp_root(), self.board(task()))
        self.assertEqual(errors, [])
        self.assertTrue(any("1.1 features" in warning or "orchestration checks are off" in warning
                            for warning in warnings), warnings)

    def test_a_corrupt_policy_is_an_error(self):
        root = temp_root()
        (root / "policy.json").write_text("{not json", encoding="utf-8")
        errors, _warnings = self.run_checks(root, self.board(task()))
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("not valid JSON", errors[0])

    def test_policy_errors_are_errors(self):
        root = self.project({"version": 1, "limits": {"max_attempts_per_task": 99},
                             "bogus": True})
        errors, _warnings = self.run_checks(root, self.board(task()))
        self.assertTrue(any("max_attempts_per_task" in error for error in errors), errors)
        self.assertTrue(any("unknown key 'bogus'" in error for error in errors), errors)

    # -- audit, approvals, run records -------------------------------------

    def test_a_done_task_without_the_chain_is_an_audit_error(self):
        root = self.project()
        board_data = self.board(task("M01", status="done"))
        errors, _warnings = self.run_checks(root, board_data)
        self.assertTrue(any("no run record runs/M01.json" in error for error in errors), errors)
        self.assertTrue(any("passing gate record for tests" in error for error in errors), errors)
        self.assertTrue(any("review file reviews/M01.md is missing" in error for error in errors),
                        errors)

    def test_pending_approvals_are_accepted(self):
        root = self.project()
        self.write_json(root, "reviews/approvals/AP-001.json", {
            "id": "AP-001", "action": "new_dependency", "task": "M01", "status": "pending",
            "requested_by": "worker", "requested_at": "2026-10-28T11:00:00+00:00",
            "approved_by": None, "approved_at": None, "note": "adds httpx",
        })
        errors, _warnings = self.run_checks(root, self.board(task()))
        self.assertEqual(errors, [])

    def test_broken_approval_records_are_errors(self):
        root = self.project()
        self.write_json(root, "reviews/approvals/AP-001.json", {
            "id": "AP-001", "action": "make_coffee", "task": "NOPE", "status": "granted",
            "requested_by": "worker", "requested_at": "2026-10-28T11:00:00+00:00",
        })
        errors, _warnings = self.run_checks(root, self.board(task()))
        self.assertTrue(any("unknown action" in error for error in errors), errors)
        self.assertTrue(any("unknown task 'NOPE'" in error for error in errors), errors)

    def test_run_records_are_validated(self):
        root = self.project()
        self.write_json(root, "runs/M01.json", {
            "task": "M02", "state": "lost", "attempt": -1,
            "attempts": [{"n": "one"}],
        })
        self.write_json(root, "runs/M99.json", {
            "task": "M99", "state": "idle", "attempt": 0, "attempts": [],
        })
        errors, _warnings = self.run_checks(root, self.board(task()))
        joined = "\n".join(errors)
        self.assertIn("runs/M01.json: task 'M02' does not match the file name 'M01'", joined)
        self.assertIn("unknown state 'lost'", joined)
        self.assertIn("attempt must be a non-negative integer", joined)
        self.assertIn("attempts[0] needs an integer n", joined)
        self.assertIn("runs/M99.json: task 'M99' is not on the board", joined)

    # -- limits and scopes -------------------------------------------------

    def test_two_in_progress_tasks_may_not_overlap_scopes(self):
        root = self.project()
        board_data = self.board(
            task("M01", status="in_progress", scope_write=["src/"]),
            task("M02", status="in_progress", scope_write=["src/db/"]),
        )
        errors, _warnings = self.run_checks(root, board_data)
        self.assertTrue(any("both in_progress with overlapping scope_write" in error
                            for error in errors), errors)

    def test_attempts_above_the_limit_are_errors(self):
        root = self.project({"version": 1, "limits": {"max_attempts_per_task": 2}})
        self.write_json(root, "runs/M01.json", {
            "task": "M01", "state": "failed", "attempt": 3,
            "attempts": [{"n": 1, "result": "fail"}, {"n": 2, "result": "fail"},
                         {"n": 3, "result": "fail"}],
        })
        errors, _warnings = self.run_checks(root, self.board(task()))
        self.assertTrue(any("3 attempts used" in error and "max_attempts_per_task is 2" in error
                            for error in errors), errors)

    # -- dispatch ----------------------------------------------------------

    def dispatch_board(self) -> dict:
        return self.board(
            task("T-01", status="pending", parallel_group="wave", scope_write=["src/"]),
            task("T-02", status="pending", parallel_group="wave", scope_write=["src/db/"]),
            task("T-03", status="pending", depends_on=["T-01"]),
        )

    def test_dispatch_conflicts_are_errors_and_blocked_tasks_are_warnings(self):
        root = self.project()
        (root / "tasks").mkdir()
        for tid in ("T-01", "T-02", "T-03"):
            (root / "tasks" / f"{tid}.md").write_text(f"# {tid} — x\n", encoding="utf-8")
        errors, warnings = self.run_checks(root, self.dispatch_board())
        self.assertTrue(any("dispatch: T-01 and T-02 share" in error for error in errors), errors)
        self.assertTrue(any("dispatch: T-03 is blocked" in warning for warning in warnings),
                        warnings)

    def test_disjoint_scopes_off_turns_the_conflict_into_no_error(self):
        root = self.project({"version": 1, "checks": {"disjoint_scopes": False}})
        (root / "tasks").mkdir()
        for tid in ("T-01", "T-02", "T-03"):
            (root / "tasks" / f"{tid}.md").write_text(f"# {tid} — x\n", encoding="utf-8")
        errors, _warnings = self.run_checks(root, self.dispatch_board())
        self.assertFalse(any("dispatch:" in error for error in errors), errors)

    # -- docs --------------------------------------------------------------

    def test_missing_doc_references_are_warnings(self):
        root = self.project(agents_text="no tool names here\n", readme_text="nothing\n",
                            orchestration=False)
        errors, warnings = self.run_checks(root, self.board(task()))
        self.assertEqual(errors, [])
        joined = "\n".join(warnings)
        self.assertIn("tools/state.py is not mentioned", joined)
        self.assertIn("docs/orchestration.md is missing", joined)
        self.assertIn("runs/ is not mentioned", joined)
        self.assertIn("policy.json is not mentioned", joined)

    def test_an_unnamed_orchestration_page_warns(self):
        root = self.project(agents_text="no tool names here\n", readme_text="nothing\n")
        errors, warnings = self.run_checks(root, self.board(task()))
        self.assertEqual(errors, [])
        self.assertTrue(any("docs/orchestration.md is not mentioned" in warning
                            for warning in warnings), warnings)


if __name__ == "__main__":
    unittest.main()
