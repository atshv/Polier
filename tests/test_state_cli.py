"""tools/state.py: show, set and check through the checkpoints of core.state."""
from __future__ import annotations

import json
import unittest

from helpers import make_project, run_tool, task


def write_policy(root, extra: dict | None = None) -> None:
    data = {"version": 1}
    data.update(extra or {})
    (root / "policy.json").write_text(json.dumps(data), encoding="utf-8")


def run(root, *args):
    return run_tool("state.py", *args, "--root", str(root))


def board_status(root, task_id: str = "M01") -> str:
    board = json.loads((root / "board.json").read_text())
    return next(entry["status"] for entry in board["tasks"] if entry.get("id") == task_id)


def run_record(root, task_id: str = "M01") -> dict:
    return json.loads((root / "runs" / f"{task_id}.json").read_text())


class Set(unittest.TestCase):
    def test_a_transition_prints_side_effects_and_the_next_checkpoint(self):
        root = make_project([task("M01", status="pending")])
        write_policy(root)
        result = run(root, "set", "M01", "in_progress")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("M01: pending → in_progress", result.stdout)
        self.assertIn("attempt 1/3", result.stdout)
        self.assertIn("round 0", result.stdout)
        self.assertIn("next: python3 tools/state.py set M01 verifying", result.stdout)
        self.assertEqual(board_status(root), "in_progress")
        self.assertEqual(run_record(root)["attempt"], 1)

    def test_actor_and_note_reach_the_run_record(self):
        root = make_project([task("M01", status="pending")])
        write_policy(root)
        self.assertEqual(run(root, "set", "M01", "in_progress", "--actor", "worker").returncode, 0)
        result = run(root, "set", "M01", "failed", "--actor", "worker",
                     "--note", "tests cannot pass")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("in_progress → failed", result.stdout)
        record = run_record(root)
        self.assertEqual(record["attempts"][0]["result"], "fail")
        self.assertEqual(record["attempts"][0]["note"], "tests cannot pass")
        self.assertEqual(record["events"][-1]["data"]["actor"], "worker")

    def test_a_note_is_required_for_blocked(self):
        root = make_project([task("M01")])
        write_policy(root)
        refused = run(root, "set", "M01", "blocked")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("note is required for blocked", refused.stdout)
        self.assertIn("action:", refused.stdout)
        applied = run(root, "set", "M01", "blocked", "--note", "needs the owner's key")
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
        record = run_record(root)
        self.assertEqual(record["state"], "blocked")
        self.assertEqual(record["events"][-1]["kind"], "escalate")

    def test_a_refusal_prints_every_blocker_and_action(self):
        root = make_project([task("M01", status="review", gates=["tests", "lint"])])
        write_policy(root)
        result = run(root, "set", "M01", "done")
        self.assertEqual(result.returncode, 1)
        self.assertIn("REFUSED M01 → done", result.stdout)
        for blocker in ("no passing gate record for tests, lint",
                        "reviews/M01.md is missing",
                        "no run record runs/M01.json"):
            self.assertIn(blocker, result.stdout)
        self.assertIn("python3 tools/gate.py --task M01 --name tests", result.stdout)
        self.assertIn("python3 tools/gate.py --task M01 --name lint", result.stdout)
        self.assertGreaterEqual(result.stdout.count("action: "), 3)
        self.assertEqual(board_status(root), "review")

    def test_the_attempt_limit_prints_the_escalation(self):
        from core import runs
        root = make_project([task("M01", status="pending")])
        write_policy(root)
        for _ in range(3):
            runs.start_attempt(root, "M01")
            runs.finish_attempt(root, "M01", "fail")
        result = run(root, "set", "M01", "in_progress")
        self.assertEqual(result.returncode, 1)
        self.assertIn("attempts 3/3 used — escalate", result.stdout)
        self.assertIn("python3 tools/state.py set M01 blocked", result.stdout)
        self.assertIn("python3 tools/approve.py request --action state_override", result.stdout)

    def test_force_needs_a_granted_override(self):
        root = make_project([task("M01", status="review")])
        write_policy(root)
        refused = run(root, "set", "M01", "done", "--force")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("state_override", refused.stdout)
        self.assertIn("approve.py", refused.stdout)

        from core import approvals
        record = approvals.request(root, "state_override", "M01")
        approvals.grant(root, record["id"], "owner")
        result = run(root, "set", "M01", "done", "--force")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("forced:", result.stdout)
        self.assertIn("done", result.stdout)

    def test_without_a_policy_the_checkpoints_only_warn(self):
        root = make_project([task("M01", status="review")])
        self.assertFalse((root / "policy.json").exists())
        result = run(root, "set", "M01", "done")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("warning:", result.stdout)
        self.assertIn("not enforced", result.stdout)
        self.assertEqual(board_status(root), "done")

    def test_the_board_status_is_written_atomically(self):
        root = make_project([task("M01", status="pending")])
        write_policy(root)
        self.assertEqual(run(root, "set", "M01", "in_progress").returncode, 0)
        self.assertEqual(sorted(path.name for path in root.iterdir()
                                if path.name.startswith("board.json")),
                         ["board.json"])
        json.loads((root / "board.json").read_text())


class Check(unittest.TestCase):
    def test_check_evaluates_without_writing(self):
        root = make_project([task("M01", status="pending")])
        write_policy(root)
        result = run(root, "check", "M01", "in_progress")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK M01 pending → in_progress", result.stdout)
        self.assertEqual(board_status(root), "pending")
        self.assertFalse((root / "runs").exists())

    def test_check_json_reports_the_evaluation(self):
        root = make_project([task("M01", status="pending")])
        write_policy(root)
        result = run(root, "check", "M01", "in_progress", "--json")
        self.assertEqual(result.returncode, 0)
        parsed = json.loads(result.stdout)
        self.assertTrue(parsed["ok"])
        self.assertEqual((parsed["from"], parsed["to"]), ("pending", "in_progress"))

    def test_a_refused_check_exits_1(self):
        root = make_project([task("M01", status="pending")])
        write_policy(root)
        result = run(root, "check", "M01", "done")
        self.assertEqual(result.returncode, 1)
        self.assertIn("REFUSED", result.stdout)
        self.assertIn("not allowed", result.stdout)
        self.assertIn("action:", result.stdout)

    def test_a_note_transition_cannot_be_checked_without_the_note(self):
        root = make_project([task("M01")])
        write_policy(root)
        result = run(root, "check", "M01", "blocked")
        self.assertEqual(result.returncode, 1)
        self.assertIn("note is required for blocked", result.stdout)

    def test_a_failed_check_with_json_still_exits_1(self):
        root = make_project([task("M01", status="pending")])
        write_policy(root)
        result = run(root, "check", "M01", "done", "--json")
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["ok"])


class Show(unittest.TestCase):
    def test_show_one_task_as_json(self):
        root = make_project([task("M01", status="pending")])
        write_policy(root)
        result = run(root, "show", "M01", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = json.loads(result.stdout)
        self.assertEqual((parsed["task"], parsed["status"], parsed["state"]),
                         ("M01", "pending", "idle"))
        self.assertEqual(parsed["gates"], ["tests"])
        self.assertFalse(parsed["review"]["present"])
        self.assertFalse(parsed["run_record"])
        self.assertTrue(parsed["policy"])

    def test_show_one_task_as_text(self):
        root = make_project([task("M01")])
        write_policy(root)
        result = run(root, "show", "M01")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("M01 Task M01", result.stdout)
        self.assertIn("status: in_progress", result.stdout)
        self.assertIn("attempt: 0/3", result.stdout)
        self.assertIn("gates: tests (missing)", result.stdout)
        self.assertIn("review: reviews/M01.md (missing)", result.stdout)
        self.assertIn("policy: on", result.stdout)

    def test_show_the_whole_board(self):
        root = make_project([task("M01", status="pending"), task("M02", status="done")])
        result = run(root, "show")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("M01", result.stdout)
        self.assertIn("M02", result.stdout)
        parsed = json.loads(run(root, "show", "--json").stdout)
        self.assertEqual((parsed["project"], parsed["profile"]), ("t", "S"))
        self.assertEqual([entry["task"] for entry in parsed["tasks"]], ["M01", "M02"])

    def test_show_without_a_policy_reports_it(self):
        root = make_project([task("M01", status="pending")])
        result = run(root, "show", "M01")
        self.assertEqual(result.returncode, 0)
        self.assertIn("policy: off", result.stdout)


class Errors(unittest.TestCase):
    def test_a_missing_board_is_an_environment_error(self):
        root = make_project([task("M01")])
        (root / "board.json").unlink()
        for args in (("show",), ("show", "M01"), ("check", "M01", "in_progress"),
                     ("set", "M01", "in_progress")):
            self.assertEqual(run(root, *args).returncode, 2, args)

    def test_an_unknown_task_is_an_environment_error_for_show(self):
        root = make_project([task("M01")])
        result = run(root, "show", "M99")
        self.assertEqual(result.returncode, 2)
        self.assertIn("M99", result.stderr)

    def test_an_unknown_task_is_a_refusal_for_set(self):
        root = make_project([task("M01")])
        write_policy(root)
        result = run(root, "set", "M99", "in_progress")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not on the board", result.stdout)

    def test_usage_errors_exit_2(self):
        root = make_project([task("M01")])
        write_policy(root)
        self.assertEqual(run(root, "set", "M01", "teleporting").returncode, 2)
        self.assertEqual(run(root, "set", "M01").returncode, 2)
        self.assertEqual(run(root, "check", "M01").returncode, 2)

    def test_a_broken_board_is_an_environment_error(self):
        root = make_project([task("M01")])
        (root / "board.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(run(root, "show", "M01").returncode, 2)
        self.assertEqual(run(root, "check", "M01", "in_progress").returncode, 2)


if __name__ == "__main__":
    unittest.main()
