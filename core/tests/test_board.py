"""Board schema 1.0: 0.9 boards stay valid, 1.0 fields are opt-in and validated."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from core.board import (
    board_errors, package_paths, resources, schema_version, stage_ids, task_id_pattern,
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


class Render(unittest.TestCase):
    def _render(self, board: dict) -> str:
        spec = importlib.util.spec_from_file_location(
            "pl_render", TOOLS / "render_status.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module.render(board)

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

    def test_classic_board_rendering_is_unchanged(self):
        text = self._render(board_09())
        self.assertIn("**Stage:** 1 of 1", text)
        self.assertNotIn("## Stages", text)
        self.assertNotIn("## Packages", text)
        self.assertNotIn("## Runtime", text)


if __name__ == "__main__":
    unittest.main()
