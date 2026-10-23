"""core.paths and core.board without any harness."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.board import active_tasks, find_root, load_board, pick_task, ready_tasks
from core.errors import PolierError
from core.paths import inside, normalized, outside, relative, resolve

from .fixtures import project, task


class Paths(unittest.TestCase):
    def test_normalized(self):
        self.assertEqual(normalized("./src//a/"), "src/a")
        self.assertEqual(normalized("src\\a.py"), "src/a.py")
        self.assertEqual(normalized("."), "")
        self.assertEqual(normalized(None), "")
        self.assertEqual(normalized("a/../../b"), "../b")

    def test_inside(self):
        self.assertTrue(inside("src/a.py", "src"))
        self.assertTrue(inside("src/a.py", "src/"))
        self.assertTrue(inside("src", "src"))
        self.assertFalse(inside("srcx/a.py", "src"))
        self.assertFalse(inside("a", ""))

    def test_outside_and_relative(self):
        root = tempfile.mkdtemp()
        self.assertEqual(relative(root, resolve(root, "src/a.py")), "src/a.py")
        self.assertEqual(relative(root, os.path.join(root, "..", "x")), "../x")
        self.assertEqual(relative(root, root), "")
        self.assertTrue(outside("../x"))
        self.assertTrue(outside("/abs"))
        self.assertTrue(outside("C:/abs"))
        self.assertFalse(outside("src"))


class Board(unittest.TestCase):
    def test_find_root_walks_up(self):
        root = project([task()], repo=False)
        (root / "src" / "deep").mkdir()
        self.assertEqual(find_root(root / "src" / "deep"), root)
        self.assertIsNone(find_root(tempfile.mkdtemp()))
        self.assertIsNone(find_root(None))

    def test_load_board_strict_and_tolerant(self):
        root = project([task()], repo=False)
        self.assertEqual(load_board(root)["tasks"][0]["id"], "M01")
        (root / "board.json").write_text("{nope")
        with self.assertRaises(PolierError):
            load_board(root)
        self.assertIsNone(load_board(root, strict=False))
        (root / "board.json").write_text("[]")
        self.assertIsNone(load_board(root, strict=False))
        empty = Path(tempfile.mkdtemp())
        with self.assertRaisesRegex(PolierError, "not found"):
            load_board(empty)
        self.assertIsNone(load_board(empty, strict=False))

    def test_pick_task(self):
        board = {"tasks": [task("M01"), task("M02", "pending")]}
        self.assertEqual(pick_task(board)["id"], "M01")
        self.assertEqual(pick_task(board, "M02")["id"], "M02")
        with self.assertRaisesRegex(PolierError, "not on the board"):
            pick_task(board, "M09")
        with self.assertRaisesRegex(PolierError, "several"):
            pick_task({"tasks": [task("M01"), task("M02")]})
        with self.assertRaisesRegex(PolierError, "no task"):
            pick_task({"tasks": [task("M01", "done")]})

    def test_active_tasks(self):
        root = Path(tempfile.mkdtemp())
        board = {"tasks": [task("M01"), task("M02", worktree="wt/M02"), task("M03", "pending")]}
        self.assertEqual(active_tasks(board, pinned="M03"), ([board["tasks"][2]], "pinned"))
        tasks, how = active_tasks(board, root=root, cwd=root / "wt" / "M02" / "src")
        self.assertEqual(([t["id"] for t in tasks], how), (["M02"], "worktree"))
        tasks, how = active_tasks(board, root=root, cwd=root)
        self.assertEqual(([t["id"] for t in tasks], how), (["M01", "M02"], "several"))
        self.assertEqual(active_tasks({"tasks": [task("M01")]})[1], "single")
        self.assertEqual(active_tasks({"tasks": []}), ([], "none"))
        self.assertEqual(active_tasks(None), ([], "none"))

    def test_ready_tasks_carry_handoffs(self):
        board = {"tasks": [
            task("M01", "done", handoff=["use uv"]),
            task("M02", "pending", depends_on=["M01"]),
            task("M03", "pending", depends_on=["M02"]),
        ]}
        self.assertEqual(ready_tasks(board), [
            {"id": "M02", "title": "Task M02", "brief": "tasks/M02.md", "handoff": ["M01: use uv"]},
        ])


if __name__ == "__main__":
    unittest.main()
