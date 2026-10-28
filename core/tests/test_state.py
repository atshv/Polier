"""core.state: the task state machine and its checkpoints (PL-20)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from core import approvals, runs, state
from core.board import STATUSES as BOARD_STATUSES
from core.errors import PolierError

from .fixtures import (gate_record, project, review_note, set_board, task,
                       write_json, write_policy)

EXPECTED_TRANSITIONS = {
    "pending": {"claimed", "in_progress", "blocked", "failed"},
    "claimed": {"pending", "in_progress", "blocked", "failed"},
    "in_progress": {"verifying", "blocked", "failed"},
    "verifying": {"review", "rework", "blocked", "failed"},
    "review": {"done", "rework", "blocked", "failed"},
    "rework": {"in_progress", "blocked", "failed"},
    "blocked": {"pending", "in_progress", "failed"},
    "failed": {"pending", "in_progress"},
    "done": {"rework"},
}


def policy_project(tasks) -> Path:
    root = project(tasks, repo=False)
    write_policy(root)
    return root


def start(root: Path) -> None:
    """Give the task an open attempt, as the transition to in_progress would."""
    runs.start_attempt(root, "M01", actor="worker")


def to_review(root: Path, tid: str = "M01") -> None:
    """pending -> in_progress -> verifying -> review, with a passing gate record."""
    state.set_status(root, tid, "in_progress", actor="worker")
    state.set_status(root, tid, "verifying")
    gate_record(root, tid, "tests")
    state.set_status(root, tid, "review")


def to_done(root: Path, tid: str = "M01") -> None:
    to_review(root, tid)
    review_note(root, tid)
    state.set_status(root, tid, "done", actor="lead")


def add_handoff(root: Path, tid: str, lines) -> None:
    board = json.loads((root / "board.json").read_text(encoding="utf-8"))
    for entry in board["tasks"]:
        if entry.get("id") == tid:
            entry["handoff"] = lines
    write_json(root / "board.json", board)


def set_round(root: Path, tid: str, value: int) -> None:
    board = json.loads((root / "board.json").read_text(encoding="utf-8"))
    for entry in board["tasks"]:
        if entry.get("id") == tid:
            entry["round"] = value
    write_json(root / "board.json", board)


def board_status(root: Path, tid: str = "M01") -> str:
    board = json.loads((root / "board.json").read_text(encoding="utf-8"))
    return next(entry["status"] for entry in board["tasks"] if entry.get("id") == tid)


def refused(testcase, *args, **kwargs) -> state.TransitionBlocked:
    with testcase.assertRaises(state.TransitionBlocked) as caught:
        state.set_status(*args, **kwargs)
    return caught.exception


class Table(unittest.TestCase):
    def test_the_transition_table_is_the_contract(self):
        self.assertEqual({key: set(value) for key, value in state.TRANSITIONS.items()},
                         EXPECTED_TRANSITIONS)
        self.assertEqual(set(state.STATUSES), BOARD_STATUSES)

    def test_a_refusal_is_a_polier_error_with_errors_and_actions(self):
        root = policy_project([task("M01", status="pending")])
        blocked = refused(self, root, "M01", "done")
        self.assertIsInstance(blocked, PolierError)
        self.assertTrue(blocked.errors)
        self.assertTrue(all(isinstance(error, str) for error in blocked.errors))
        self.assertTrue(blocked.actions)
        for action in blocked.actions:
            self.assertEqual(set(action), {"action", "command", "reason"})
            self.assertTrue(action["command"].startswith(
                ("python3 tools/", "reviews/", "runs/", "board.json")))


class Compatibility(unittest.TestCase):
    def test_without_policy_no_checkpoint_blocks_a_transition(self):
        root = project([task("M01", status="pending")], repo=False)
        self.assertFalse((root / "policy.json").exists())
        state.set_status(root, "M01", "in_progress")
        state.set_status(root, "M01", "verifying")
        state.set_status(root, "M01", "review")
        result = state.set_status(root, "M01", "done")
        self.assertEqual((result["to"], result["state"]), ("done", "done"))
        self.assertTrue(any("not enforced" in warning for warning in result["warnings"]),
                        result["warnings"])
        self.assertEqual(board_status(root), "done")

    def test_without_policy_the_attempt_limit_is_not_enforced(self):
        root = project([task("M01", status="pending")], repo=False)
        for expected_attempt in range(1, 6):
            result = state.set_status(root, "M01", "in_progress")
            self.assertEqual(result["attempt"], expected_attempt)
            state.set_status(root, "M01", "failed", note="boom")
        self.assertEqual(runs.attempt_count(root, "M01"), 5)

    def test_the_transition_table_and_notes_always_apply(self):
        root = project([task("M01", status="pending")], repo=False)
        blocked = refused(self, root, "M01", "done")
        self.assertIn("not allowed", blocked.errors[0])
        blocked = refused(self, root, "M01", "verifying")
        self.assertIn("not allowed", blocked.errors[0])
        state.set_status(root, "M01", "in_progress")
        blocked = refused(self, root, "M01", "failed")
        self.assertIn("note is required", blocked.errors[0])


class Checking(unittest.TestCase):
    def test_a_check_never_writes(self):
        root = policy_project([task("M01", status="pending")])
        result = state.check_transition(root, None, "M01", "in_progress")
        self.assertTrue(result["ok"])
        self.assertEqual((result["from"], result["to"]), ("pending", "in_progress"))
        self.assertEqual(board_status(root), "pending")
        self.assertFalse((root / "runs").exists())

    def test_unknown_task_status_and_transition(self):
        root = policy_project([task("M01", status="pending")])
        unknown = state.check_transition(root, None, "M99", "in_progress")
        self.assertFalse(unknown["ok"])
        self.assertIn("not on the board", unknown["errors"][0])
        bad_status = state.check_transition(root, None, "M01", "teleporting")
        self.assertFalse(bad_status["ok"])
        self.assertIn("unknown status", bad_status["errors"][0])
        bad_current = state.check_transition(root, None, {"id": "M01", "status": "weird"}, "in_progress")
        self.assertFalse(bad_current["ok"])
        self.assertIn("unknown", bad_current["errors"][0])

    def test_a_stopped_stage_blocks_everything(self):
        tasks = [task("M01", status="pending", stage="a")]
        root = project(tasks, repo=False)
        set_board(root, schema_version="1.0",
                  stages=[{"id": "a", "title": "A", "owner_decision": "stop"}], tasks=tasks)
        write_policy(root)
        result = state.check_transition(root, None, "M01", "in_progress")
        self.assertFalse(result["ok"])
        self.assertIn("stopped by the owner", result["errors"][0])

    def test_a_stage_behind_its_dependencies_blocks_in_progress(self):
        tasks = [task("M01", status="pending", stage="a"),
                 task("M02", status="pending", stage="b")]
        root = project(tasks, repo=False)
        set_board(root, schema_version="1.0",
                  stages=[{"id": "a", "title": "A", "owner_decision": "pending"},
                          {"id": "b", "title": "B", "depends_on": ["a"]}], tasks=tasks)
        write_policy(root)
        result = state.check_transition(root, None, "M02", "in_progress")
        self.assertFalse(result["ok"])
        self.assertIn("needs stage(s) a complete first", result["errors"][0])

    def test_verifying_needs_an_open_attempt(self):
        root = policy_project([task("M01", status="in_progress")])
        result = state.check_transition(root, None, "M01", "verifying")
        self.assertFalse(result["ok"])
        self.assertIn("no open attempt", result["errors"][0])
        self.assertTrue(any("tools/state.py" in action["command"] for action in result["actions"]))
        start(root)
        self.assertTrue(state.check_transition(root, None, "M01", "verifying")["ok"])

    def test_review_needs_a_passing_record_for_every_gate(self):
        root = policy_project([task("M01", status="verifying")])
        start(root)
        result = state.check_transition(root, None, "M01", "review")
        self.assertFalse(result["ok"])
        self.assertIn("no passing gate record for tests", result["errors"][0])
        self.assertTrue(any("tools/gate.py --task M01 --name tests" in action["command"]
                            for action in result["actions"]))
        gate_record(root, "M01", "tests", result="infra", exit_code=1)
        self.assertFalse(state.check_transition(root, None, "M01", "review")["ok"])
        gate_record(root, "M02", "tests")           # another task's record does not count
        self.assertFalse(state.check_transition(root, None, "M01", "review")["ok"])
        gate_record(root, "M01", "tests")
        self.assertTrue(state.check_transition(root, None, "M01", "review")["ok"])

    def test_done_needs_the_evidence_chain(self):
        root = policy_project([task("M01", status="review")])
        start(root)
        gate_record(root, "M01", "tests")
        missing_review = state.check_transition(root, None, "M01", "done")
        self.assertFalse(missing_review["ok"])
        self.assertIn("reviews/M01.md is missing", missing_review["errors"][0])
        review_note(root, "M01", verdict="fail")
        failed_review = state.check_transition(root, None, "M01", "done")
        self.assertFalse(failed_review["ok"])
        self.assertIn("verdict: fail", failed_review["errors"][0])
        review_note(root, "M01")
        self.assertTrue(state.check_transition(root, None, "M01", "done")["ok"])

    def test_done_needs_a_run_record(self):
        root = policy_project([task("M01", status="review")])
        gate_record(root, "M01", "tests")
        review_note(root, "M01")
        result = state.check_transition(root, None, "M01", "done")
        self.assertFalse(result["ok"])
        self.assertIn("no run record", result["errors"][0])

    def test_done_needs_a_handoff_when_tasks_depend_on_it(self):
        root = policy_project([task("M01", status="review"),
                               task("M02", status="pending", depends_on=["M01"])])
        start(root)
        gate_record(root, "M01", "tests")
        review_note(root, "M01")
        result = state.check_transition(root, None, "M01", "done")
        self.assertFalse(result["ok"])
        self.assertIn("no handoff", result["errors"][0])
        add_handoff(root, "M01", ["api: stable", "db: no change"])
        self.assertTrue(state.check_transition(root, None, "M01", "done")["ok"])

    def test_done_needs_approval_for_a_dependency_manifest(self):
        root = policy_project([task("M01", status="review", scope_write=["package.json"])])
        start(root)
        gate_record(root, "M01", "tests")
        review_note(root, "M01")
        result = state.check_transition(root, None, "M01", "done")
        self.assertFalse(result["ok"])
        self.assertIn("dependency manifest 'package.json'", result["errors"][0])
        self.assertTrue(any("tools/approve.py request --action new_dependency" in action["command"]
                            for action in result["actions"]))
        approval = approvals.request(root, "new_dependency", "M01")
        approvals.grant(root, approval["id"], "owner")
        self.assertTrue(state.check_transition(root, None, "M01", "done")["ok"])

    def test_attempt_limit_blocks_another_in_progress(self):
        root = policy_project([task("M01", status="pending")])
        for _ in range(3):
            state.set_status(root, "M01", "in_progress")
            state.set_status(root, "M01", "failed", note="boom")
        result = state.check_transition(root, None, "M01", "in_progress")
        self.assertFalse(result["ok"])
        self.assertIn("attempts 3/3 used", result["errors"][0])
        commands = " ".join(action["command"] for action in result["actions"])
        self.assertIn("python3 tools/state.py show M01 --json", commands)
        self.assertIn("python3 tools/approve.py request --action state_override", commands)

    def test_max_in_progress_blocks_another_start(self):
        root = policy_project([task("M01", status="in_progress"),
                               task("M02", status="in_progress"),
                               task("M03", status="pending")])
        result = state.check_transition(root, None, "M03", "in_progress")
        self.assertFalse(result["ok"])
        self.assertIn("2 task(s) already in_progress", result["errors"][0])
        self.assertTrue(any("wait" == action["action"] for action in result["actions"]))

    def test_note_requirements(self):
        root = policy_project([task("M01", status="in_progress")])
        start(root)
        failed = state.check_transition(root, None, "M01", "failed")
        self.assertFalse(failed["ok"])
        self.assertIn("note is required for failed", failed["errors"][0])
        blocked = state.check_transition(root, None, "M01", "blocked")
        self.assertFalse(blocked["ok"])
        self.assertIn("note is required for blocked", blocked["errors"][0])
        state.set_status(root, "M01", "verifying")
        rework = state.check_transition(root, None, "M01", "rework")
        self.assertFalse(rework["ok"])
        self.assertIn("note is required for rework", rework["errors"][0])

    def test_round_limit_blocks_another_rework(self):
        root = policy_project([task("M01", status="verifying")])
        start(root)
        set_round(root, "M01", 3)
        result = state.check_transition(root, None, "M01", "rework", note="again")
        self.assertFalse(result["ok"])
        self.assertIn("round 4 would exceed max_review_rounds 3", result["errors"][0])

    def test_a_done_task_needs_reopen_approval(self):
        root = policy_project([task("M01", status="pending")])
        to_done(root)
        result = state.check_transition(root, None, "M01", "rework", note="reopen")
        self.assertFalse(result["ok"])
        self.assertIn("reopen_done", result["errors"][0])
        approval = approvals.request(root, "reopen_done", "M01")
        approvals.grant(root, approval["id"], "owner")
        self.assertTrue(state.check_transition(root, None, "M01", "rework", note="reopen")["ok"])

    def test_force_needs_an_override_and_bypasses_the_checkpoints(self):
        root = policy_project([task("M01", status="review")])
        start(root)
        result = state.check_transition(root, None, "M01", "done", force=True)
        self.assertFalse(result["ok"])
        self.assertIn("forced change needs a granted state_override approval", result["errors"][-1])
        approval = approvals.request(root, "state_override", "M01")
        approvals.grant(root, approval["id"], "owner")
        result = state.check_transition(root, None, "M01", "done", force=True)
        self.assertTrue(result["ok"])
        self.assertTrue(result["warnings"])
        self.assertTrue(all(warning.startswith("forced: ") for warning in result["warnings"]))
        self.assertTrue(result["forced"])

    def test_force_does_not_bypass_the_transition_table(self):
        root = policy_project([task("M01", status="pending")])
        approval = approvals.request(root, "state_override", "M01")
        approvals.grant(root, approval["id"], "owner")
        result = state.check_transition(root, None, "M01", "done", force=True)
        self.assertFalse(result["ok"])
        self.assertIn("not allowed", result["errors"][0])


class SideEffects(unittest.TestCase):
    def test_the_full_chain_records_attempts_and_events(self):
        root = policy_project([task("M01", status="pending")])
        state.set_status(root, "M01", "in_progress", actor="worker")
        state.set_status(root, "M01", "verifying")
        gate_record(root, "M01", "tests")
        state.set_status(root, "M01", "review")
        review_note(root, "M01")
        result = state.set_status(root, "M01", "done", actor="lead", note="all green")
        self.assertEqual(result["attempt"], 1)
        self.assertEqual(result["state"], "done")
        record = runs.load_run(root, "M01")
        self.assertEqual((record["state"], record["attempt"]), ("done", 1))
        self.assertEqual(record["attempts"][0]["result"], "pass")
        self.assertIsNotNone(record["attempts"][0]["ended"])
        self.assertEqual([event["kind"] for event in record["events"]],
                         ["start", "state", "state", "state", "state"])
        self.assertEqual(record["events"][-1]["data"],
                         {"from": "review", "to": "done", "actor": "lead",
                          "note": "all green"})
        self.assertEqual(board_status(root), "done")

    def test_claimed_can_go_back_to_pending(self):
        root = policy_project([task("M01", status="claimed")])
        self.assertEqual(state.set_status(root, "M01", "pending")["to"], "pending")
        self.assertEqual(board_status(root), "pending")

    def test_blocked_closes_the_attempt_and_escalates(self):
        root = policy_project([task("M01", status="pending")])
        state.set_status(root, "M01", "in_progress")
        result = state.set_status(root, "M01", "blocked", note="needs the owner's key")
        self.assertEqual(result["state"], "blocked")
        record = runs.load_run(root, "M01")
        self.assertEqual(record["attempts"][0]["result"], "cancelled")
        self.assertEqual(record["attempts"][0]["note"], "needs the owner's key")
        self.assertEqual(record["events"][-1]["kind"], "escalate")
        self.assertEqual(board_status(root), "blocked")

    def test_failed_closes_the_attempt_as_fail(self):
        root = policy_project([task("M01", status="pending")])
        state.set_status(root, "M01", "in_progress")
        state.set_status(root, "M01", "failed", note="tests cannot pass")
        record = runs.load_run(root, "M01")
        self.assertEqual((record["attempts"][0]["result"], record["state"]),
                         ("fail", "failed"))

    def test_rework_increments_the_round_and_closes_the_attempt(self):
        root = policy_project([task("M01", status="pending")])
        state.set_status(root, "M01", "in_progress")
        state.set_status(root, "M01", "verifying")
        result = state.set_status(root, "M01", "rework", note="two blockers")
        self.assertEqual((result["round"], result["state"]), (1, "failed"))
        self.assertEqual(board_status(root), "rework")
        record = runs.load_run(root, "M01")
        self.assertEqual(record["attempts"][0]["result"], "fail")
        self.assertEqual(record["attempts"][0]["note"], "two blockers")
        result = state.set_status(root, "M01", "in_progress")
        self.assertEqual((result["attempt"], result["round"]), (2, 1))
        state.set_status(root, "M01", "verifying")
        result = state.set_status(root, "M01", "rework", note="still blocked")
        self.assertEqual(result["round"], 2)

    def test_reopen_of_a_done_task(self):
        root = policy_project([task("M01", status="pending")])
        to_done(root)
        refused(self, root, "M01", "rework", note="reopen")
        approval = approvals.request(root, "reopen_done", "M01")
        approvals.grant(root, approval["id"], "owner")
        result = state.set_status(root, "M01", "rework", note="reopen")
        self.assertEqual((result["from"], result["to"], result["round"]), ("done", "rework", 1))
        self.assertEqual(board_status(root), "rework")

    def test_a_forced_change_records_a_warning_event(self):
        root = policy_project([task("M01", status="review")])
        start(root)
        approval = approvals.request(root, "state_override", "M01")
        approvals.grant(root, approval["id"], "owner")
        result = state.set_status(root, "M01", "done", force=True)
        self.assertEqual(result["to"], "done")
        self.assertTrue(result["warnings"])
        warnings = [event for event in runs.load_run(root, "M01")["events"]
                    if event["kind"] == "note" and "warning" in event["data"]]
        self.assertEqual(len(warnings), 1)
        self.assertIn("forced transition review → done", warnings[0]["data"]["warning"])
        self.assertTrue(warnings[0]["data"]["overridden"])

    def test_forced_in_progress_bypasses_the_attempt_limit(self):
        root = policy_project([task("M01", status="pending")])
        for _ in range(3):
            state.set_status(root, "M01", "in_progress")
            state.set_status(root, "M01", "failed", note="boom")
        refused(self, root, "M01", "in_progress")
        approval = approvals.request(root, "state_override", "M01")
        approvals.grant(root, approval["id"], "owner")
        result = state.set_status(root, "M01", "in_progress", force=True)
        self.assertEqual((result["to"], result["attempt"]), ("in_progress", 4))

    def test_a_corrupt_run_file_is_tolerated(self):
        root = policy_project([task("M01", status="pending")])
        path = runs.run_path(root, "M01")
        path.parent.mkdir(parents=True)
        path.write_text("{this is not a run record", encoding="utf-8")
        result = state.set_status(root, "M01", "in_progress")
        self.assertEqual(result["attempt"], 1)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["attempt"], 1)
        state.set_status(root, "M01", "verifying")
        self.assertEqual(runs.run_state(root, "M01"), "running")

    def test_the_board_is_written_atomically(self):
        root = policy_project([task("M01", status="pending")])
        state.set_status(root, "M01", "in_progress")
        self.assertEqual(
            sorted(name for name in (root / "board.json").parent.iterdir()
                   if name.name.startswith("board.json")),
            [root / "board.json"])
        json.loads((root / "board.json").read_text(encoding="utf-8"))
        self.assertFalse(any(path.name.endswith(".tmp") for path in (root / "runs").iterdir()))

    def test_result_fields(self):
        root = policy_project([task("M01", status="pending")])
        result = state.set_status(root, "M01", "in_progress")
        self.assertEqual(result["max_attempts"], 3)
        self.assertEqual(result["next"], "python3 tools/state.py set M01 verifying")
        self.assertEqual(result["to"], "in_progress")
        self.assertEqual(result["from"], "pending")
        self.assertTrue(result["ok"])

    def test_set_status_refuses_an_invalid_task(self):
        root = policy_project([task("M01", status="pending")])
        with self.assertRaises(PolierError):
            state.set_status(root, "", "in_progress")
        with self.assertRaises(state.TransitionBlocked):
            state.set_status(root, "M99", "in_progress")
        self.assertEqual(board_status(root), "pending")


class StatusOf(unittest.TestCase):
    def test_status_of_reports_the_checkpoint_state(self):
        root = policy_project([task("M01", status="pending", handoff=["deps: none"])])
        to_review(root)
        review_note(root, "M01")
        status = state.status_of(root, "M01")
        self.assertEqual((status["task"], status["status"], status["state"]),
                         ("M01", "review", "running"))
        self.assertEqual((status["attempt"], status["attempts"], status["max_attempts"]),
                         (1, 1, 3))
        self.assertEqual(status["gates"], ["tests"])
        self.assertEqual(status["passed"], ["tests"])
        self.assertEqual(status["missing_gates"], [])
        self.assertTrue(status["review"]["present"])
        self.assertEqual(status["review"]["verdict"], "pass")
        self.assertTrue(status["run_record"])
        self.assertTrue(status["policy"])
        self.assertEqual(status["handoff"], ["deps: none"])

    def test_status_of_before_anything_happened(self):
        root = policy_project([task("M01", status="pending")])
        status = state.status_of(root, "M01")
        self.assertEqual((status["state"], status["attempt"], status["run_record"]),
                         ("idle", 0, False))
        self.assertEqual(status["missing_gates"], ["tests"])
        self.assertIsNone(status["review"]["verdict"])
        self.assertFalse(status["review"]["present"])

    def test_status_of_an_unknown_task(self):
        root = policy_project([task("M01")])
        with self.assertRaises(PolierError):
            state.status_of(root, "M99")


if __name__ == "__main__":
    unittest.main()
