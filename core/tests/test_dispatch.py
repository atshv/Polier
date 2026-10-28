"""core.dispatch: waves, conflicts, blocked tasks and running tasks of the board."""
from __future__ import annotations

import unittest
from pathlib import Path

from core import claims, runs
from core.dispatch import plan
from core.errors import PolierError

from .fixtures import project, set_board, task, write_policy


def briefs(root: Path, *task_ids: str) -> None:
    """Write tasks/<ID>.md for the given tasks (a candidate without one is blocked)."""
    folder = root / "tasks"
    folder.mkdir(exist_ok=True)
    for task_id in task_ids:
        (folder / f"{task_id}.md").write_text(f"# {task_id}\n", encoding="utf-8")


def ids(entries) -> list:
    return [entry.get("id") for entry in entries]


def wave_ids(result: dict) -> list:
    return [ids(wave) for wave in result.get("waves") or []]


class Shape(unittest.TestCase):
    def test_the_result_shape_is_the_design_contract(self):
        root = project([task("M01", status="pending")], repo=False)
        briefs(root, "M01")
        write_policy(root)
        result = plan(root)
        self.assertEqual(set(result), {"project", "profile", "limits", "running", "waves",
                                       "blocked", "conflicts", "approvals_pending", "next"})
        self.assertEqual(set(result["limits"]), {"max_attempts_per_task", "max_in_progress"})
        self.assertEqual((result["project"], result["profile"]), ("t", "S"))
        self.assertEqual(result["limits"], {"max_attempts_per_task": 3, "max_in_progress": 2})

    def test_the_limits_come_from_the_policy(self):
        root = project([task("M01", status="pending")], repo=False)
        briefs(root, "M01")
        write_policy(root, {"limits": {"max_attempts_per_task": 5, "max_in_progress": 4}})
        self.assertEqual(plan(root)["limits"],
                         {"max_attempts_per_task": 5, "max_in_progress": 4})

    def test_a_wave_entry_names_the_task_its_brief_and_its_group(self):
        root = project([task("M01", status="pending", parallel_group="db")], repo=False)
        briefs(root, "M01")
        write_policy(root)
        entry = plan(root)["waves"][0][0]
        self.assertEqual(entry, {"id": "M01", "title": "Task M01", "brief": "tasks/M01.md",
                                 "parallel_group": "db"})

    def test_without_a_board_the_plan_raises(self):
        root = project([task("M01", status="pending")], repo=False)
        (root / "board.json").unlink()
        with self.assertRaises(PolierError):
            plan(root)

    def test_a_broken_policy_is_treated_as_absent(self):
        root = project([task("M01", status="pending")], repo=False)
        briefs(root, "M01")
        (root / "policy.json").write_text("{not json", encoding="utf-8")
        result = plan(root)
        self.assertEqual(wave_ids(result), [["M01"]])

    def test_an_empty_board_has_no_next_wave(self):
        root = project([task("M01", status="done")], repo=False)
        write_policy(root)
        result = plan(root)
        self.assertEqual((result["waves"], result["next"], result["running"]), ([], [], []))


class Waves(unittest.TestCase):
    def test_same_group_same_stage_and_disjoint_scopes_share_a_wave(self):
        root = project([
            task("M01", status="pending", parallel_group="db", scope_write=["src/db/"]),
            task("M02", status="pending", parallel_group="db", scope_write=["src/api/"]),
        ], repo=False)
        briefs(root, "M01", "M02")
        write_policy(root)
        result = plan(root)
        self.assertEqual(wave_ids(result), [["M01", "M02"]])
        self.assertEqual(result["next"], ["M01", "M02"])
        self.assertEqual(result["conflicts"], [])

    def test_a_task_without_a_group_is_a_wave_of_its_own(self):
        root = project([
            task("M01", status="pending"),
            task("M02", status="pending"),
        ], repo=False)
        briefs(root, "M01", "M02")
        write_policy(root)
        self.assertEqual(wave_ids(plan(root)), [["M01"], ["M02"]])

    def test_different_groups_do_not_share_a_wave(self):
        root = project([
            task("M01", status="pending", parallel_group="db"),
            task("M02", status="pending", parallel_group="api"),
        ], repo=False)
        briefs(root, "M01", "M02")
        write_policy(root)
        self.assertEqual(wave_ids(plan(root)), [["M01"], ["M02"]])

    def test_the_same_group_in_another_stage_does_not_share_a_wave(self):
        stages = [{"id": "a", "title": "A", "owner_decision": "continue"},
                  {"id": "b", "title": "B", "owner_decision": "continue"}]
        root = project([
            task("M01", status="pending", stage="a", parallel_group="db"),
            task("M02", status="pending", stage="b", parallel_group="db"),
        ], repo=False)
        set_board(root, schema_version="1.0", stages=stages)
        briefs(root, "M01", "M02")
        write_policy(root)
        self.assertEqual(wave_ids(plan(root)), [["M01"], ["M02"]])

    def test_groups_are_packed_up_to_max_in_progress(self):
        root = project([
            task("M01", status="pending", parallel_group="db", scope_write=["a/"]),
            task("M02", status="pending", parallel_group="db", scope_write=["b/"]),
            task("M03", status="pending", parallel_group="db", scope_write=["c/"]),
        ], repo=False)
        briefs(root, "M01", "M02", "M03")
        write_policy(root, {"limits": {"max_in_progress": 2}})
        result = plan(root)
        self.assertEqual(wave_ids(result), [["M01", "M02"], ["M03"]])
        self.assertEqual(result["next"], ["M01", "M02"])

    def test_the_limit_caps_the_tasks_per_wave(self):
        root = project([
            task("M01", status="pending", parallel_group="db", scope_write=["a/"]),
            task("M02", status="pending", parallel_group="db", scope_write=["b/"]),
        ], repo=False)
        briefs(root, "M01", "M02")
        write_policy(root)
        result = plan(root, limit=1)
        self.assertEqual(wave_ids(result), [["M01"], ["M02"]])

    def test_a_deeper_limit_wins_over_the_policy(self):
        root = project([
            task("M01", status="pending", parallel_group="db", scope_write=["a/"]),
            task("M02", status="pending", parallel_group="db", scope_write=["b/"]),
        ], repo=False)
        briefs(root, "M01", "M02")
        write_policy(root, {"limits": {"max_in_progress": 2}})
        self.assertEqual(wave_ids(plan(root, limit=1)), [["M01"], ["M02"]])

    def test_non_pending_tasks_are_not_wave_members(self):
        root = project([
            task("M01", status="done"),
            task("M02", status="review"),
            task("M03", status="failed"),
            task("M04", status="pending"),
        ], repo=False)
        briefs(root, "M04")
        write_policy(root)
        self.assertEqual(wave_ids(plan(root)), [["M04"]])


class Conflicts(unittest.TestCase):
    def fixture(self, **scopes) -> Path:
        tasks = [
            task("M01", status="pending", parallel_group="db",
                 scope_write=scopes.get("first", ["src/db/"])),
            task("M02", status="pending", parallel_group="db",
                 scope_write=scopes.get("second", ["src/db/schema.py"])),
        ]
        root = project(tasks, repo=False)
        briefs(root, "M01", "M02")
        write_policy(root, {"limits": {"max_in_progress": 4}})
        return root

    def test_an_overlapping_scope_is_a_conflict_and_only_the_first_stays(self):
        root = self.fixture()
        result = plan(root)
        self.assertEqual(wave_ids(result), [["M01"]])
        self.assertEqual(result["conflicts"], [
            {"a": "M01", "b": "M02", "paths": ["src/db/", "src/db/schema.py"]},
        ])

    def test_scopes_that_only_look_alike_are_not_a_conflict(self):
        root = self.fixture(first=["src/db/"], second=["src/database/"])
        result = plan(root)
        self.assertEqual(wave_ids(result), [["M01", "M02"]])
        self.assertEqual(result["conflicts"], [])

    def test_a_sibling_file_does_not_conflict(self):
        root = self.fixture(first=["src/app.py"], second=["src/other.py"])
        self.assertEqual(wave_ids(plan(root)), [["M01", "M02"]])

    def test_disjoint_scopes_false_keeps_the_task_in_the_wave(self):
        root = self.fixture()
        write_policy(root, {"limits": {"max_in_progress": 4},
                            "checks": {"disjoint_scopes": False}})
        result = plan(root)
        self.assertEqual(wave_ids(result), [["M01", "M02"]])
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertEqual(result["conflicts"][0]["a"], "M01")

    def test_a_conflict_does_not_spill_into_the_next_wave(self):
        root = project([
            task("M01", status="pending", parallel_group="db", scope_write=["src/db/"]),
            task("M02", status="pending", parallel_group="db", scope_write=["src/db/x.py"]),
            task("M03", status="pending", parallel_group="db", scope_write=["src/db/y.py"]),
        ], repo=False)
        briefs(root, "M01", "M02", "M03")
        write_policy(root, {"limits": {"max_in_progress": 3}})
        result = plan(root)
        self.assertEqual(wave_ids(result), [["M01"]])
        self.assertEqual([conflict["b"] for conflict in result["conflicts"]], ["M02", "M03"])


class Running(unittest.TestCase):
    def test_an_in_progress_task_reports_its_attempt(self):
        root = project([task("M01", status="in_progress")], repo=False)
        runs.start_attempt(root, "M01")
        runs.start_attempt(root, "M01")
        write_policy(root)
        entry = plan(root)["running"][0]
        self.assertEqual(entry, {"id": "M01", "title": "Task M01", "status": "in_progress",
                                 "attempt": 2, "max_attempts": 3, "claim": None})

    def test_every_active_status_is_running(self):
        root = project([
            task("M01", status="claimed"),
            task("M02", status="verifying"),
            task("M03", status="review"),
            task("M04", status="rework"),
        ], repo=False)
        write_policy(root)
        self.assertEqual(ids(plan(root)["running"]), ["M01", "M02", "M03", "M04"])

    def test_a_live_claim_on_a_ready_task_is_running_not_a_wave_member(self):
        root = project([task("M01", status="pending")], repo=True)
        briefs(root, "M01")
        write_policy(root)
        claims.take(root, "M01", harness="dsh", session="session-1")
        result = plan(root)
        self.assertEqual(result["waves"], [])
        self.assertEqual(result["running"], [{
            "id": "M01", "title": "Task M01", "status": "pending", "attempt": 0,
            "max_attempts": 3, "claim": {"harness": "dsh", "session": "session-1"},
        }])

    def test_a_claim_on_an_active_task_is_shown(self):
        root = project([task("M01", status="in_progress")], repo=True)
        runs.start_attempt(root, "M01")
        write_policy(root)
        claims.take(root, "M01", harness="claude-code", session="s-2")
        entry = plan(root)["running"][0]
        self.assertEqual(entry["claim"], {"harness": "claude-code", "session": "s-2"})


class Blocked(unittest.TestCase):
    def test_an_exhausted_attempt_count_is_blocked_with_the_escalation(self):
        root = project([task("M01", status="pending")], repo=False)
        briefs(root, "M01")
        write_policy(root)
        for _ in range(3):
            runs.start_attempt(root, "M01")
            runs.finish_attempt(root, "M01", "fail")
        result = plan(root)
        self.assertEqual(result["waves"], [])
        self.assertEqual(len(result["blocked"]), 1)
        entry = result["blocked"][0]
        self.assertEqual(entry["id"], "M01")
        self.assertEqual(entry["reason"], "attempts 3/3 used — escalate")
        self.assertIn("tools/state.py set M01 blocked", entry["action"])

    def test_the_attempt_limit_needs_a_policy(self):
        root = project([task("M01", status="pending")], repo=False)
        briefs(root, "M01")
        for _ in range(4):
            runs.start_attempt(root, "M01")
            runs.finish_attempt(root, "M01", "fail")
        result = plan(root)
        self.assertEqual(wave_ids(result), [["M01"]])
        self.assertEqual(result["blocked"], [])

    def test_a_missing_brief_blocks_a_ready_task(self):
        root = project([task("M01", status="pending")], repo=False)
        write_policy(root)
        result = plan(root)
        self.assertEqual(result["waves"], [])
        self.assertEqual(result["blocked"], [{
            "id": "M01", "reason": "brief tasks/M01.md is missing",
            "action": "write tasks/M01.md"}])

    def test_a_pending_task_waits_for_its_dependencies(self):
        root = project([
            task("M01", status="pending"),
            task("M02", status="pending", depends_on=["M01"]),
        ], repo=False)
        briefs(root, "M01", "M02")
        write_policy(root)
        result = plan(root)
        self.assertEqual(wave_ids(result), [["M01"]])
        self.assertEqual(result["blocked"], [{
            "id": "M02", "reason": "waits for M01",
            "action": "python3 tools/state.py show M01 --json"}])

    def test_a_stopped_stage_blocks_its_tasks(self):
        stages = [{"id": "a", "title": "A", "owner_decision": "stop"}]
        root = project([task("M01", status="pending", stage="a")], repo=False)
        set_board(root, schema_version="1.0", stages=stages)
        briefs(root, "M01")
        write_policy(root)
        entry = plan(root)["blocked"][0]
        self.assertEqual(entry["reason"], "stage stopped by the owner")
        self.assertIn("tools/state.py show M01", entry["action"])

    def test_a_task_of_a_stage_behind_its_dependencies_waits(self):
        stages = [{"id": "a", "title": "A", "owner_decision": "pending"},
                  {"id": "b", "title": "B", "owner_decision": "continue",
                   "depends_on": ["a"]}]
        root = project([task("M02", status="pending", stage="b")], repo=False)
        set_board(root, schema_version="1.0", stages=stages)
        briefs(root, "M02")
        write_policy(root)
        entry = plan(root)["blocked"][0]
        self.assertEqual(entry["reason"], "stage waits for a")

    def test_a_claim_on_a_task_that_is_not_ready_is_blocked(self):
        root = project([
            task("M01", status="pending"),
            task("M02", status="pending", depends_on=["M01"]),
        ], repo=True)
        briefs(root, "M01", "M02")
        write_policy(root)
        claims.take(root, "M02", harness="dsh", session="s-3")
        result = plan(root)
        entry = next(item for item in result["blocked"] if item["id"] == "M02")
        self.assertEqual(entry["reason"], "claimed by another session (dsh)")

    def test_non_pending_tasks_are_not_blocked_entries(self):
        root = project([
            task("M01", status="done"),
            task("M02", status="failed"),
            task("M03", status="blocked"),
        ], repo=False)
        write_policy(root)
        self.assertEqual(plan(root)["blocked"], [])


class Approvals(unittest.TestCase):
    def test_pending_approvals_are_listed(self):
        root = project([task("M01", status="pending")], repo=False)
        briefs(root, "M01")
        write_policy(root)
        from core import approvals
        first = approvals.request(root, "new_dependency", "M01")
        second = approvals.request(root, "release", None)
        result = plan(root)
        self.assertEqual(result["approvals_pending"], [
            {"id": first["id"], "action": "new_dependency", "task": "M01"},
            {"id": second["id"], "action": "release", "task": None},
        ])

    def test_a_granted_approval_is_not_pending(self):
        root = project([task("M01", status="pending")], repo=False)
        briefs(root, "M01")
        write_policy(root)
        from core import approvals
        record = approvals.request(root, "new_dependency", "M01")
        approvals.grant(root, record["id"], "owner")
        self.assertEqual(plan(root)["approvals_pending"], [])


class Compatibility(unittest.TestCase):
    def test_a_project_without_policy_still_gets_a_plan(self):
        root = project([task("M01", status="pending")], repo=False)
        briefs(root, "M01")
        result = plan(root)
        self.assertEqual(wave_ids(result), [["M01"]])
        self.assertEqual(result["limits"], {"max_attempts_per_task": 3, "max_in_progress": 2})
        self.assertFalse((root / "policy.json").exists())


if __name__ == "__main__":
    unittest.main()
