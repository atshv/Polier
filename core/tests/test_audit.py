"""core.audit: the compliance view of the board and the tools/audit.py CLI."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from core import approvals, runs
from core.audit import audit, audit_task
from core.errors import PolierError

from .fixtures import (gate_record, project, review_note, set_board, task,
                       write_policy)

TOOLS = Path(__file__).resolve().parents[2] / "tools"


def complete(root: Path, task_id: str = "M01") -> None:
    """Give a done task the full chain: gate record, review, run record."""
    gate_record(root, task_id, "tests")
    review_note(root, task_id)
    runs.start_attempt(root, task_id)
    runs.finish_attempt(root, task_id, "pass")


def cli(root: Path, *args):
    return subprocess.run(
        [sys.executable, str(TOOLS / "audit.py"), *args, "--root", str(root)],
        capture_output=True, text=True, check=False)


class Shape(unittest.TestCase):
    def fixture(self) -> tuple:
        root = project([task("M01", status="pending")], repo=False)
        write_policy(root)
        return root, audit(root)

    def test_the_result_shape(self):
        _root, result = self.fixture()
        self.assertEqual(set(result), {"tasks", "errors", "warnings"})
        self.assertEqual(len(result["tasks"]), 1)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["warnings"], [])

    def test_the_task_record_shape(self):
        _root, result = self.fixture()
        record = result["tasks"][0]
        for key in ("task", "title", "status", "attempts", "max_attempts", "gates",
                    "passed", "missing_gates", "review", "handoff", "approvals",
                    "run_record", "dependency_manifest", "findings", "errors",
                    "warnings"):
            self.assertIn(key, record)
        self.assertEqual((record["task"], record["status"]), ("M01", "pending"))
        self.assertEqual((record["attempts"], record["max_attempts"]), (0, 3))
        self.assertEqual(record["gates"], ["tests"])
        self.assertEqual(record["missing_gates"], ["tests"])
        self.assertEqual(record["review"],
                         {"file": "reviews/M01.md", "present": False, "verdict": None})
        self.assertFalse(record["run_record"])
        self.assertEqual(record["findings"], [])

    def test_approvals_are_reported_per_policy_action(self):
        _root, result = self.fixture()
        entries = {entry["action"]: entry for entry in result["tasks"][0]["approvals"]}
        self.assertEqual(set(entries), {"new_dependency", "scope_change", "merge_to_base",
                                        "release", "reopen_done", "protected_path"})
        self.assertTrue(all(entry["status"] == "none" for entry in entries.values()))

    def test_audit_task_accepts_a_task_and_an_id(self):
        root, _result = self.fixture()
        board = json.loads((root / "board.json").read_text())
        self.assertEqual(audit_task(root, board, "M01", {"enabled": False})["task"], "M01")
        self.assertEqual(audit_task(root, board, board["tasks"][0], {"enabled": False})["task"],
                         "M01")
        with self.assertRaises(PolierError):
            audit_task(root, board, "M99", {"enabled": False})


class DoneTasks(unittest.TestCase):
    def policy_done(self, tasks=None) -> Path:
        root = project(tasks or [task("M01", status="done")], repo=False)
        write_policy(root)
        return root

    def test_a_complete_done_task_has_no_findings(self):
        root = self.policy_done()
        complete(root)
        result = audit(root)
        self.assertEqual((result["errors"], result["warnings"]), ([], []))
        self.assertEqual(result["tasks"][0]["findings"], [])

    def test_a_done_task_without_a_review_is_an_error(self):
        root = self.policy_done()
        gate_record(root, "M01", "tests")
        runs.start_attempt(root, "M01")
        result = audit(root)
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("review file reviews/M01.md is missing", result["errors"][0])
        self.assertEqual(result["tasks"][0]["errors"], result["errors"])

    def test_a_failing_review_verdict_is_an_error(self):
        root = self.policy_done()
        complete(root)
        review_note(root, "M01", verdict="fail")
        result = audit(root)
        self.assertTrue(any("verdict: fail" in error for error in result["errors"]))

    def test_a_missing_gate_record_is_an_error(self):
        root = self.policy_done()
        review_note(root, "M01")
        runs.start_attempt(root, "M01")
        result = audit(root)
        self.assertTrue(any("no passing gate record for tests" in error
                            for error in result["errors"]))
        self.assertEqual(result["tasks"][0]["missing_gates"], ["tests"])

    def test_an_infrastructure_gate_record_does_not_count(self):
        root = self.policy_done()
        review_note(root, "M01")
        runs.start_attempt(root, "M01")
        gate_record(root, "M01", "tests", result="infra", exit_code=1)
        result = audit(root)
        self.assertTrue(any("no passing gate record for tests" in error
                            for error in result["errors"]))

    def test_a_missing_run_record_is_an_error(self):
        root = self.policy_done()
        gate_record(root, "M01", "tests")
        review_note(root, "M01")
        result = audit(root)
        self.assertTrue(any("no run record runs/M01.json" in error
                            for error in result["errors"]))

    def test_a_done_task_that_others_depend_on_needs_a_handoff(self):
        root = self.policy_done([task("M01", status="done"),
                                 task("M02", status="pending", depends_on=["M01"])])
        complete(root)
        result = audit(root)
        self.assertTrue(any("no handoff" in error and "M02" in error
                            for error in result["errors"]))
        set_board(root, tasks=[task("M01", status="done", handoff=["api: stable"]),
                               task("M02", status="pending", depends_on=["M01"])])
        self.assertFalse(any("handoff" in error for error in audit(root)["errors"]))

    def test_a_manifest_write_needs_an_approval(self):
        root = self.policy_done([task("M01", status="done", scope_write=["package.json"])])
        complete(root)
        result = audit(root)
        self.assertTrue(any("dependency manifest 'package.json'" in error
                            for error in result["errors"]))
        record = approvals.request(root, "new_dependency", "M01")
        approvals.grant(root, record["id"], "owner")
        self.assertEqual(audit(root)["errors"], [])

    def test_disabled_checks_produce_no_findings(self):
        root = self.policy_done([task("M01", status="done", gates=[])])
        write_policy(root, {"checks": {"review_before_done": False,
                                       "handoff_before_done": False,
                                       "run_record": False}})
        self.assertEqual(audit(root)["errors"], [])
        self.assertEqual(audit(root)["tasks"][0]["findings"], [])

    def test_an_attempt_count_over_the_limit_is_an_error_for_a_done_task(self):
        root = self.policy_done()
        complete(root)
        for _ in range(3):
            runs.start_attempt(root, "M01")
        findings = audit(root)["tasks"][0]["findings"]
        self.assertIn(("attempts", "error"),
                      [(finding["check"], finding["severity"]) for finding in findings])
        self.assertTrue(any("attempts 4/3 used" in error for error in audit(root)["errors"]))


class OtherStatuses(unittest.TestCase):
    def test_a_missing_gate_on_a_review_task_is_a_warning(self):
        root = project([task("M01", status="review")], repo=False)
        write_policy(root)
        result = audit(root)
        self.assertEqual(result["errors"], [])
        checks = [(finding["check"], finding["severity"])
                  for finding in result["tasks"][0]["findings"]]
        self.assertIn(("gates", "warning"), checks)

    def test_an_attempt_count_over_the_limit_is_a_warning_before_done(self):
        root = project([task("M01", status="pending")], repo=False)
        write_policy(root)
        for _ in range(4):
            runs.start_attempt(root, "M01")
        result = audit(root)
        self.assertEqual(result["errors"], [])
        self.assertTrue(any("attempts 4/3 used" in warning for warning in result["warnings"]))

    def test_a_manifest_without_an_approval_warns_on_a_running_task(self):
        root = project([task("M01", status="in_progress", scope_write=["package.json"]),
                        ], repo=False)
        write_policy(root)
        result = audit(root)
        self.assertEqual(result["errors"], [])
        self.assertTrue(any("new_dependency" in warning for warning in result["warnings"]))

    def test_the_approval_state_is_visible(self):
        root = project([task("M01", status="in_progress")], repo=False)
        write_policy(root)
        record = approvals.request(root, "new_dependency", "M01")
        entries = {entry["action"]: entry
                   for entry in audit(root)["tasks"][0]["approvals"]}
        self.assertEqual(entries["new_dependency"],
                         {"action": "new_dependency", "status": "pending",
                          "id": record["id"]})
        approvals.grant(root, record["id"], "owner")
        entries = {entry["action"]: entry
                   for entry in audit(root)["tasks"][0]["approvals"]}
        self.assertEqual(entries["new_dependency"]["status"], "granted")


class Compatibility(unittest.TestCase):
    def test_without_a_policy_a_done_task_only_warns(self):
        root = project([task("M01", status="done")], repo=False)
        result = audit(root)
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(result["warnings"]), 3)
        self.assertTrue(all("not enforced" in warning for warning in result["warnings"]))

    def test_a_complete_done_task_is_clean_without_a_policy(self):
        root = project([task("M01", status="done")], repo=False)
        complete(root)
        result = audit(root)
        self.assertEqual((result["errors"], result["warnings"]), ([], []))

    def test_an_explicitly_disabled_policy_behaves_like_a_missing_one(self):
        root = project([task("M01", status="done")], repo=False)
        result = audit(root, policy={"enabled": False})
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(result["warnings"]), 3)

    def test_a_broken_policy_is_a_warning_not_a_failure(self):
        root = project([task("M01", status="pending")], repo=False)
        (root / "policy.json").write_text("{not json", encoding="utf-8")
        result = audit(root)
        self.assertEqual(result["errors"], [])
        self.assertTrue(any("policy.json cannot be used" in warning
                            for warning in result["warnings"]))

    def test_without_a_board_the_audit_raises(self):
        root = project([task("M01", status="pending")], repo=False)
        (root / "board.json").unlink()
        with self.assertRaises(PolierError):
            audit(root)


class Cli(unittest.TestCase):
    def test_a_done_task_with_a_missing_chain_exits_1(self):
        root = project([task("M01", status="done")], repo=False)
        write_policy(root)
        result = cli(root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("M01", result.stdout)
        self.assertIn("ERRORS", result.stdout)
        self.assertIn("no passing gate record for tests", result.stdout)
        self.assertIn("run record", result.stdout)

    def test_json_prints_the_audit_dict(self):
        root = project([task("M01", status="done")], repo=False)
        write_policy(root)
        result = cli(root, "--json")
        self.assertEqual(result.returncode, 1)
        parsed = json.loads(result.stdout)
        self.assertEqual(set(parsed), {"tasks", "errors", "warnings"})
        self.assertEqual(parsed["tasks"][0]["task"], "M01")

    def test_task_restricts_the_view_and_the_exit_code(self):
        root = project([task("M01", status="pending"),
                        task("M02", status="done")], repo=False)
        write_policy(root)
        blocked = cli(root, "--task", "M01")
        self.assertEqual(blocked.returncode, 0, blocked.stdout)
        self.assertNotIn("M02", blocked.stdout)
        failing = cli(root, "--task", "M02")
        self.assertEqual(failing.returncode, 1)
        self.assertIn("M02", failing.stdout)

    def test_without_a_policy_warnings_keep_the_exit_code_0(self):
        root = project([task("M01", status="done")], repo=False)
        result = cli(root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ERRORS: none", result.stdout)
        self.assertIn("not enforced", result.stdout)

    def test_environment_errors_exit_2(self):
        root = project([task("M01", status="pending")], repo=False)
        (root / "board.json").unlink()
        self.assertEqual(cli(root).returncode, 2)
        root = project([task("M01", status="pending")], repo=False)
        self.assertEqual(cli(root, "--task", "M99").returncode, 2)

    def test_the_clean_done_task_exits_0(self):
        root = project([task("M01", status="done")], repo=False)
        write_policy(root)
        complete(root)
        result = cli(root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ERRORS: none", result.stdout)
        self.assertIn("audit: 0 error(s), 0 warning(s)", result.stdout)


if __name__ == "__main__":
    unittest.main()
