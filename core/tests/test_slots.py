"""Runtime slots (PL-02): temporary git repos with two linked worktrees."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core.errors import PolierError
from core.slots import acquire, list_slots, load_slot, registry_path, release, slot_path

from .fixtures import git, project, set_board, task

REPO = Path(__file__).resolve().parents[2]
RESOURCES = {
    "slots": 3,
    "port_base": 4000,
    "port_stride": 100,
    "services": {"web": 0, "api": 1},
}


def configure(root: Path, resources: dict = None) -> None:
    set_board(root, schema_version="1.0", resources=dict(resources or RESOURCES))


def add_worktree(root: Path, name: str) -> Path:
    """A linked worktree on its own branch, outside the main checkout."""
    target = Path(tempfile.mkdtemp(prefix="pl-wt-")).resolve() / name
    git(root, "worktree", "add", "-q", "-b", f"task/{name}", str(target), "main")
    return target


class Acquire(unittest.TestCase):
    def setUp(self):
        self.root = project([task()])
        configure(self.root)

    def test_two_worktrees_get_different_slots_and_disjoint_ports(self):
        first_tree = add_worktree(self.root, "a")
        second_tree = add_worktree(self.root, "b")

        first = acquire(first_tree)
        second = acquire(second_tree)

        self.assertEqual((first["slot"], second["slot"]), (1, 2))
        self.assertEqual(first["ports"], {"web": 4100, "api": 4101})
        self.assertEqual(second["ports"], {"web": 4200, "api": 4201})
        self.assertEqual(set(first["ports"].values()) & set(second["ports"].values()), set())
        self.assertEqual(first["worktree"], str(first_tree))
        self.assertEqual(second["worktree"], str(second_tree))
        self.assertEqual(first["project"], "t")
        self.assertEqual(first["db_name"], "t_slot_1")
        self.assertEqual(first["bucket"], "t-slot-1")
        self.assertEqual(load_slot(first_tree), first)
        self.assertEqual(load_slot(second_tree), second)

        registry = json.loads(registry_path(self.root).read_text())
        self.assertEqual(registry["version"], 1)
        self.assertEqual(sorted(registry["slots"]), ["1", "2"])
        self.assertEqual([entry["slot"] for entry in list_slots(self.root)], [1, 2])

    def test_existing_slot_is_reused_and_registered_again(self):
        tree = add_worktree(self.root, "a")
        first = acquire(tree)
        again = acquire(tree)
        self.assertEqual(first["slot"], again["slot"])
        self.assertEqual(len(json.loads(registry_path(self.root).read_text())["slots"]), 1)

        registry_path(self.root).unlink()  # e.g. the repo was restored from a backup
        repaired = acquire(tree)
        self.assertEqual(repaired["slot"], first["slot"])
        self.assertEqual([entry["slot"] for entry in list_slots(self.root)], [first["slot"]])

    def test_release_removes_file_and_registry_entry(self):
        tree = add_worktree(self.root, "a")
        data = acquire(tree)
        released = release(tree)
        self.assertEqual(released["slot"], data["slot"])
        self.assertFalse(slot_path(tree).exists())
        self.assertEqual(list_slots(self.root), [])
        self.assertIsNone(release(tree))

    def test_main_checkout_gets_slot_zero_without_registration(self):
        main = acquire(self.root)
        self.assertEqual(main["slot"], 0)
        self.assertEqual(main["ports"], {"web": 4000, "api": 4001})
        self.assertEqual(main["db_name"], "t_slot_0")
        self.assertEqual(main["bucket"], "t-slot-0")
        self.assertEqual(main["worktree"], str(self.root))
        self.assertTrue(slot_path(self.root).is_file())
        self.assertEqual(list_slots(self.root), [])
        self.assertFalse(registry_path(self.root).exists())

        self.assertEqual(acquire(self.root)["slot"], 0)
        released = release(self.root)
        self.assertEqual(released["slot"], 0)
        self.assertFalse(slot_path(self.root).exists())

    def test_outside_git_raises(self):
        outside = Path(tempfile.mkdtemp(prefix="pl-nogit-")).resolve()
        with self.assertRaises(PolierError):
            acquire(outside)
        with self.assertRaises(PolierError):
            list_slots(outside)

    def test_all_slots_taken_raises_and_changes_nothing(self):
        configure(self.root, {"slots": 2, "port_base": 4000, "port_stride": 100,
                              "services": {"web": 0}})
        first_tree = add_worktree(self.root, "a")
        second_tree = add_worktree(self.root, "b")
        acquire(first_tree)
        registry_before = registry_path(self.root).read_text()

        with self.assertRaises(PolierError) as caught:
            acquire(second_tree)
        self.assertIn("free slot", str(caught.exception))
        self.assertFalse(slot_path(second_tree).exists())
        self.assertEqual(registry_path(self.root).read_text(), registry_before)

    def test_deleted_worktree_is_stale_and_reclaimed(self):
        first_tree = add_worktree(self.root, "a")
        second_tree = add_worktree(self.root, "b")
        acquire(first_tree)
        acquire(second_tree)
        shutil.rmtree(second_tree)

        listed = {entry["slot"]: entry for entry in list_slots(self.root)}
        self.assertFalse(listed[1]["stale"])
        self.assertTrue(listed[2]["stale"])
        self.assertEqual(listed[2]["worktree"], str(second_tree))

        third_tree = add_worktree(self.root, "c")
        with self.assertRaises(PolierError):
            acquire(third_tree)  # without --reclaim-stale a registered slot still counts
        reclaimed = acquire(third_tree, reclaim_stale=True)
        self.assertEqual(reclaimed["slot"], 2)
        self.assertEqual(reclaimed["worktree"], str(third_tree))
        self.assertFalse(any(entry["stale"] for entry in list_slots(self.root)))
        self.assertEqual(load_slot(third_tree), reclaimed)
        self.assertFalse(slot_path(second_tree).exists())

    def test_parallel_acquires_never_share_a_slot(self):
        first_tree = add_worktree(self.root, "a")
        second_tree = add_worktree(self.root, "b")
        script = (
            "import sys\n"
            f"sys.path.insert(0, {str(REPO)!r})\n"
            "from core.slots import acquire\n"
            "print(acquire(sys.argv[1])['slot'])\n"
        )
        processes = [
            subprocess.Popen([sys.executable, "-c", script, str(tree)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for tree in (first_tree, second_tree)
        ]
        outputs = [process.communicate(timeout=60) for process in processes]
        for process, (_, stderr) in zip(processes, outputs):
            self.assertEqual(process.returncode, 0, stderr)
        slots = {int(stdout.strip()) for stdout, _ in outputs}
        self.assertEqual(len(slots), 2)


if __name__ == "__main__":
    unittest.main()
