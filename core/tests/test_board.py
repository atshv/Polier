"""Board schemas: 0.9 stays valid, 1.0 and 1.1 fields are opt-in and validated."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from core.board import (
    board_errors, package_paths, ready_tasks, resources, schema_version, stage_ids,
    stage_report, task_id_pattern,
)

TOOLS = Path(__file__).resolve().parents[2] / "tools"


def _task(tid: str = "M01", **extra) -> dict:
    data = {
        "id": tid, "title": f"Task {tid}", "goal": "Do it.", "status": "pending",
        "depends_on": [], "complexity": 3, "stage": 1,
        "scope_write": ["src/app.py"], "acceptance": ["A1"], "gates": ["tests"],
    }
    data.update(extra)
    return data


def board_09(tasks: list | None = None) -> dict:
    return {
        "project": "t", "profile": "S", "base_branch": "main",
        "generator_version": "0.9.0", "stage": 1,
        "tasks": tasks or [_task()],
    }


def board_10() -> dict:
    return {
        "project": "suite", "profile": "L", "base_branch": "main",
        "generator_version": "1.0.0", "schema_version": "1.0", "stage": 1,
        "stages": [
            {"id": "foundation", "title": "Foundation", "goal": "Scaffold",
             "exit_criteria": ["CI green"], "exit_gates": ["tests"], "owner_decision": "pending",
             "depends_on": []},
            {"id": "engine", "title": "Engine", "goal": "WASM spike",
             "exit_criteria": ["60 fps"], "exit_gates": ["wasm-build"],
             "owner_decision": "pending", "depends_on": ["foundation"]},
        ],
        "packages": [
            {"path": "packages/core", "kind": "package", "may_import": []},
            {"path": "apps/web", "kind": "app", "may_import": ["packages/core"]},
        ],
        "resources": {"slots": 4, "port_base": 4100, "port_stride": 50,
                      "services": {"web": 0, "api": 1},
                      "infra_patterns": ["ECONNREFUSED"]},
        "worktrees": "required",
        "tasks": [
            _task("P3-02", package="packages/core", stage="foundation",
                  exclusive=["e2e"], resources=["ports", "db"]),
            _task("ENG-14", package="apps/web", stage="engine",
                  depends_on=["P3-02"],
                  claim={"harness": "dsh", "session": "s1", "heartbeat": "2026-10-25T00:00:00Z"}),
        ],
    }


def board_12() -> dict:
    board = board_11()
    board["schema_version"] = "1.2"
    board["tasks"][0]["planned_start"] = "2026-11-02"
    board["tasks"][0]["target"] = "2026-11-06"
    return board


def board_11() -> dict:
    board = board_10()
    board["schema_version"] = "1.1"
    board["tasks"][0]["labels"] = ["feature", "risk-high"]
    board["tasks"][0]["estimate_hours"] = 6.5
    return board


def check_module():
    spec = importlib.util.spec_from_file_location("pl_check", TOOLS / "check.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Schema09(unittest.TestCase):
    def test_classic_board_is_valid(self):
        self.assertEqual(board_errors(board_09()), [])
        self.assertEqual(schema_version(board_09()), "0.9")

    def test_1_0_field_needs_schema_version(self):
        board = board_09([_task(package="packages/core")])
        errors = board_errors(board)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("set schema_version to 1.0", errors[0])
        # Same answer from tools/check.py, so the CLI exits 1 with that message.
        self.assertIn("set schema_version to 1.0", "\n".join(errors))

    def test_new_id_pattern_needs_schema_version(self):
        errors = board_errors(board_09([_task("P3-02")]))
        self.assertTrue(any("id must match" in error for error in errors), errors)

    def test_named_stage_needs_schema_version(self):
        errors = board_errors(board_09([_task(stage="foundation")]))
        self.assertTrue(any("schema_version to 1.0" in error for error in errors), errors)

    def test_unknown_fields_are_errors(self):
        board = board_09()
        board["mystery"] = 1
        self.assertIn("unknown field 'mystery'", "\n".join(board_errors(board)))
        board = board_09([_task(mystery=1)])
        self.assertIn("unknown field 'mystery'", "\n".join(board_errors(board)))

    def test_declared_schema_version_must_be_known(self):
        board = board_09()
        board["schema_version"] = "2.0"
        self.assertIn("unknown schema_version", "\n".join(board_errors(board)))
        board["schema_version"] = "0.9"
        self.assertIn("schema_version 0.9 is written by omitting the field",
                      "\n".join(board_errors(board)))


class Schema10(unittest.TestCase):
    def test_rich_board_is_valid(self):
        errors = board_errors(board_10())
        self.assertEqual(errors, [])
        self.assertEqual(schema_version(board_10()), "1.0")
        self.assertEqual(stage_ids(board_10()), ["foundation", "engine"])
        self.assertEqual(package_paths(board_10()), ["packages/core", "apps/web"])
        self.assertEqual(resources(board_10())["services"], {"web": 0, "api": 1})

    def test_unknown_stage_is_named(self):
        board = board_10()
        board["tasks"][0]["stage"] = "nowhere"
        errors = board_errors(board)
        self.assertTrue(any("unknown stage 'nowhere'" in error for error in errors), errors)

    def test_unknown_package_is_named(self):
        board = board_10()
        board["tasks"][1]["package"] = "apps/mobile"
        errors = board_errors(board)
        self.assertTrue(any("unknown package 'apps/mobile'" in error for error in errors), errors)

    def test_stage_shape(self):
        board = board_10()
        board["stages"][0]["owner_decision"] = "maybe"
        self.assertIn("owner_decision", "\n".join(board_errors(board)))
        board = board_10()
        board["stages"].append({"id": "foundation", "title": "Again"})
        self.assertIn("duplicate stage id", "\n".join(board_errors(board)))
        board = board_10()
        board["stages"][1]["depends_on"] = ["nope"]
        self.assertIn("unknown stage dependency 'nope'", "\n".join(board_errors(board)))

    def test_package_shape(self):
        board = board_10()
        board["packages"][0]["kind"] = "library"
        self.assertIn("kind must be one of", "\n".join(board_errors(board)))

    def test_resources_shape(self):
        board = board_10()
        board["resources"]["port_stride"] = 0
        self.assertIn("port_stride must be a positive integer", "\n".join(board_errors(board)))
        board = board_10()
        board["resources"]["services"] = {"web": "0"}
        self.assertIn("non-negative integer offset", "\n".join(board_errors(board)))

    def test_budget_needs_a_reason(self):
        board = board_10()
        board["budgets"] = {"status": {"limit": 850}}
        self.assertIn("without a reason", "\n".join(board_errors(board)))
        board["budgets"] = {"status": {"limit": 850, "reason": "32 tasks in stage 2"}}
        self.assertEqual(board_errors(board), [])
        board["budgets"] = {"nonsense": {"limit": 1, "reason": "x"}}
        self.assertIn("unknown budget 'nonsense'", "\n".join(board_errors(board)))

    def test_worktrees_enum(self):
        board = board_10()
        board["worktrees"] = "always"
        self.assertIn("worktrees must be one of", "\n".join(board_errors(board)))

    def test_claim_shape(self):
        board = board_10()
        board["tasks"][1]["claim"] = {"harness": "dsh", "session": "s", "bogus": 1}
        self.assertIn("claim has unknown field 'bogus'", "\n".join(board_errors(board)))

    def test_id_pattern_widened(self):
        pattern = task_id_pattern(board_10())
        for good in ("M01", "M123", "P3-02", "ENG-14", "A-01", "ABCDEF-99"):
            self.assertTrue(pattern.match(good), good)
        for bad in ("m01", "P3_02", "TOOLONG-01", "P3-2", "3-02", ""):
            self.assertFalse(pattern.match(bad), bad)


def stage_board(status_a: str = "done", status_b: str = "pending") -> dict:
    """One declared stage with two tasks; no exit gates, so only the tasks decide."""
    return {
        "project": "t", "profile": "M", "base_branch": "main",
        "generator_version": "1.1.0", "schema_version": "1.0", "stage": 1,
        "stages": [{"id": "s1", "title": "Stage 1", "goal": "go",
                    "exit_criteria": [], "exit_gates": [],
                    "owner_decision": "continue", "depends_on": []}],
        "tasks": [
            _task("T-01", status=status_a, stage="s1", scope_write=["src/a.py"]),
            _task("T-02", status=status_b, stage="s1", scope_write=["src/b.py"]),
        ],
    }


class StageTasksOpen(unittest.TestCase):
    """1.1: a stage is complete only when none of its tasks is still open."""

    def test_tasks_open_lists_the_ids_that_are_not_done(self):
        report = {entry["id"]: entry for entry in stage_report(stage_board())}
        self.assertEqual(report["s1"]["tasks_open"], ["T-02"])
        self.assertFalse(report["s1"]["complete"])

    def test_all_tasks_done_completes_the_stage(self):
        report = {entry["id"]: entry for entry in stage_report(
            stage_board("done", "done"))}
        self.assertEqual(report["s1"]["tasks_open"], [])
        self.assertTrue(report["s1"]["complete"])

    def test_ready_tasks_behaviour_is_unchanged(self):
        # T-02 is pending and has no dependencies: it stays ready even though
        # the stage has an open task (work in progress) and is not complete.
        board = stage_board("in_progress", "pending")
        report = {entry["id"]: entry for entry in stage_report(board)}
        self.assertEqual(report["s1"]["tasks_open"], ["T-01", "T-02"])
        self.assertFalse(report["s1"]["complete"])
        self.assertEqual([entry["id"] for entry in ready_tasks(board)], ["T-02"])

    def test_done_dependency_keeps_a_later_task_ready_in_an_open_stage(self):
        board = stage_board("done", "pending")
        board["tasks"][1]["depends_on"] = ["T-01"]
        self.assertEqual([entry["id"] for entry in ready_tasks(board)], ["T-02"])


class CheckCli(unittest.TestCase):
    """tools/check.py uses the same validation: exit 1 names the problem."""

    def test_check_board_accepts_1_0(self):
        module = check_module()
        root = Path(tempfile.mkdtemp(prefix="pl-board-")).resolve()
        (root / "board.json").write_text(json.dumps(board_10()), encoding="utf-8")
        errors: list[str] = []
        warnings: list[str] = []
        module.check_board(root, errors, warnings)
        self.assertEqual(errors, [])

    def test_check_board_names_unknown_reference(self):
        module = check_module()
        root = Path(tempfile.mkdtemp(prefix="pl-board-")).resolve()
        board = board_10()
        board["tasks"][0]["package"] = "services/ghost"
        (root / "board.json").write_text(json.dumps(board), encoding="utf-8")
        errors: list[str] = []
        module.check_board(root, errors, [])
        self.assertTrue(any("services/ghost" in error for error in errors), errors)


class Schema11(unittest.TestCase):
    def test_board_1_1_accepts_labels_and_estimate(self):
        errors = board_errors(board_11())
        self.assertEqual(errors, [])
        self.assertEqual(schema_version(board_11()), "1.1")

    def test_1_1_fields_need_schema_1_1(self):
        board = board_10()
        board["tasks"][0]["labels"] = ["feature"]
        errors = board_errors(board)
        self.assertTrue(any("needs schema version 1.1" in error for error in errors), errors)
        board = board_10()
        board["tasks"][0]["estimate_hours"] = 2
        self.assertTrue(any("needs schema version 1.1" in error
                            for error in board_errors(board)))

    def test_label_and_estimate_shape(self):
        board = board_11()
        board["tasks"][0]["labels"] = ["Feature", "risk-high"]
        self.assertTrue(any("lowercase label ids" in error for error in board_errors(board)))
        board = board_11()
        board["tasks"][0]["labels"] = ["bug", "bug"]
        self.assertTrue(any("must not repeat" in error for error in board_errors(board)))
        board = board_11()
        board["tasks"][0]["estimate_hours"] = -1
        self.assertTrue(any("estimate_hours" in error for error in board_errors(board)))
        board = board_11()
        board["tasks"][0]["estimate_hours"] = "6"
        self.assertTrue(any("estimate_hours" in error for error in board_errors(board)))

    def test_id_pattern_is_widened_for_1_1(self):
        board = board_11()
        self.assertEqual(task_id_pattern(board).pattern, task_id_pattern(board_10()).pattern)


class Schema12(unittest.TestCase):
    def test_board_1_2_accepts_planning_dates(self):
        self.assertEqual(board_errors(board_12()), [])
        self.assertEqual(schema_version(board_12()), "1.2")

    def test_1_2_fields_need_schema_1_2(self):
        board = board_11()
        board["tasks"][0]["planned_start"] = "2026-11-02"
        self.assertTrue(any("needs schema version 1.2" in error for error in board_errors(board)))
        board = board_11()
        board["tasks"][0]["target"] = "2026-11-02"
        self.assertTrue(any("needs schema version 1.2" in error for error in board_errors(board)))

    def test_date_shape_and_order(self):
        board = board_12()
        board["tasks"][0]["planned_start"] = "02.11.2026"
        self.assertTrue(any("YYYY-MM-DD" in error for error in board_errors(board)))
        board = board_12()
        board["tasks"][0]["planned_start"] = "2026-11-06"
        board["tasks"][0]["target"] = "2026-11-02"
        self.assertTrue(any("target must not be before" in error for error in board_errors(board)))


class Render(unittest.TestCase):
    def _render(self, board: dict, root=None) -> str:
        spec = importlib.util.spec_from_file_location(
            "pl_render", TOOLS / "render_status.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module.render(board, root)

    def test_renders_stages_packages_resources(self):
        text = self._render(board_10())
        self.assertIn("## Stages", text)
        self.assertIn("`foundation` Foundation", text)
        self.assertIn("Owner decision: `pending`", text)
        self.assertIn("## Packages", text)
        self.assertIn("`apps/web` — kind: `app`", text)
        self.assertIn("## Runtime", text)
        self.assertIn("4100 + 50·N", text)
        self.assertIn("`P3-02`", text)

    def test_tasks_open_is_shown_only_when_non_empty(self):
        text = self._render(stage_board("in_progress", "pending"))
        self.assertIn("- Tasks open: T-01, T-02", text)
        complete = self._render(stage_board("done", "done"))
        self.assertIn("### Stage 1 — `s1` Stage 1", complete)
        self.assertNotIn("Tasks open:", complete)

    def test_live_claims_are_shown_and_ignored_by_the_freshness_check(self):
        from core.board import load_board
        from core.claims import take
        from core.tests.fixtures import project, task as fixture_task
        root = project([fixture_task("M01")])
        take(root, "M01", harness="dsh", session="s1")
        board = load_board(root)
        text = self._render(board, root)
        self.assertIn("in progress by dsh", text)
        self.assertIn("`M01`", text)
        spec = importlib.util.spec_from_file_location(
            "pl_render_claims", TOOLS / "render_status.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        self.assertEqual(module.strip_claims(text).strip(),
                         module.render(board, root, with_claims=False).strip())
        self.assertNotIn("polier:claims", module.strip_claims(text))

    def test_orchestration_section_needs_a_policy_or_runs(self):
        from core.board import load_board
        from core.tests.fixtures import project, task as fixture_task, write_policy
        root = project([fixture_task("M01", status="pending")])
        board = load_board(root)
        self.assertNotIn("## Orchestration", self._render(board, root))
        write_policy(root)
        text = self._render(board, root)
        self.assertIn("## Orchestration", text)
        self.assertIn("- Limits: 3 attempts/task, 2 in progress", text)
        self.assertIn("- Next wave: none", text)
        self.assertIn("- Running: none", text)
        self.assertIn("- Approvals pending: none", text)

    def test_orchestration_shows_running_attempts_and_live_claims(self):
        from core.board import load_board
        from core.claims import take
        from core.runs import start_attempt
        from core.tests.fixtures import project, task as fixture_task, write_policy
        root = project([fixture_task("M01", status="in_progress"),
                        fixture_task("M02", status="pending")])
        write_policy(root)
        (root / "tasks").mkdir()
        (root / "tasks" / "M02.md").write_text("# M02 — next\n", encoding="utf-8")
        start_attempt(root, "M01")
        take(root, "M01", harness="dsh", session="s1")
        board = load_board(root)

        spec = importlib.util.spec_from_file_location(
            "pl_render_orchestration", TOOLS / "render_status.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        text = module.render(board, root)
        self.assertIn("- Running: `M01` attempt 1/3", text)
        self.assertIn("claimed by dsh", text)
        self.assertIn("- Next wave: `M02` (tasks/M02.md)", text)

        section = text[text.index("## Orchestration"):]
        section = section[:section.index("\n## ")].strip().splitlines()
        self.assertLessEqual(len(section), 10, section)
        # The claim lives inside the claims markers, so the freshness check is stable.
        self.assertEqual(module.strip_claims(text).strip(),
                         module.render(board, root, with_claims=False).strip())

    def test_classic_board_rendering_is_unchanged(self):
        text = self._render(board_09())
        self.assertIn("**Stage:** 1 of 1", text)
        self.assertNotIn("## Stages", text)
        self.assertNotIn("## Packages", text)
        self.assertNotIn("## Runtime", text)


if __name__ == "__main__":
    unittest.main()
