"""core.claims and tools/claim.py: cross-harness task claims with a heartbeat (PL-04)."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from core.claims import (CLAIM_FIELDS, ClaimConflict, NoClaim, beat, claim_dir, is_live,
                         live_claims, parse_time, read_claim, release, take)
from core.errors import PolierError

from .fixtures import git, project, task

PACKAGE = Path(__file__).resolve().parents[2]
TOOL = PACKAGE / "tools" / "claim.py"
OLD = "2020-01-01T00:00:00+00:00"


def claim_path(root: Path, task_id: str = "M01") -> Path:
    return claim_dir(root) / f"{task_id}.json"


def write_claim(root: Path, claim: dict) -> Path:
    path = claim_path(root, str(claim["task"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(claim, indent=2), encoding="utf-8")
    return path


def full_claim(task_id: str = "M01", session: str = "s1", harness: str = "dsh", **extra) -> dict:
    claim = {
        "task": task_id, "harness": harness, "session": session,
        "worktree": None, "slot": None, "started": OLD, "heartbeat": OLD,
    }
    claim.update(extra)
    return claim


def cli(*args: str, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True, cwd=cwd, check=False)


class TakeRelease(unittest.TestCase):
    def test_take_writes_the_claim_file(self):
        root = project([task()])
        claim = take(root, "M01", harness="dsh", session="agent-1", worktree="/p/repo-M01", slot=2)
        self.assertEqual(set(claim), set(CLAIM_FIELDS))
        self.assertEqual((claim["task"], claim["harness"], claim["session"]),
                         ("M01", "dsh", "agent-1"))
        self.assertEqual((claim["worktree"], claim["slot"]), ("/p/repo-M01", 2))
        stored = json.loads(claim_path(root).read_text(encoding="utf-8"))
        self.assertEqual(stored, claim)
        self.assertIsNotNone(parse_time(claim["started"]))
        self.assertIsNotNone(parse_time(claim["heartbeat"]))
        self.assertIn(".git", str(claim_path(root)))
        self.assertTrue(str(claim_path(root)).endswith("/polier/claims/M01.json"))

    def test_take_without_worktree_and_slot_stores_nulls(self):
        root = project([task()])
        claim = take(root, "M01", harness="cli", session="plain")
        self.assertIsNone(claim["worktree"])
        self.assertIsNone(claim["slot"])

    def test_same_session_refreshes_instead_of_conflicting(self):
        root = project([task()])
        write_claim(root, full_claim())
        claim = take(root, "M01", harness="dsh", session="s1")
        self.assertEqual(claim["started"], OLD)          # the claim keeps its start time
        self.assertNotEqual(claim["heartbeat"], OLD)     # only the heartbeat moved
        self.assertTrue(claim["heartbeat"] > OLD)

    def test_another_live_session_conflicts_and_names_the_holder(self):
        root = project([task()])
        take(root, "M01", harness="dsh", session="agent-1")
        with self.assertRaises(ClaimConflict) as caught:
            take(root, "M01", harness="claude-code", session="claude-9")
        message = str(caught.exception)
        self.assertIn("claimed by", message)
        self.assertIn("dsh", message)
        self.assertIn("agent-1", message)
        self.assertEqual(read_claim(root, "M01")["session"], "agent-1")

    def test_a_stale_claim_can_be_taken_over(self):
        root = project([task()])
        write_claim(root, full_claim())
        self.assertFalse(is_live(read_claim(root, "M01")))
        claim = take(root, "M01", harness="claude-code", session="claude-9", ttl=600)
        self.assertEqual(claim["session"], "claude-9")
        self.assertEqual(claim["started"], claim["heartbeat"])

    def test_release(self):
        root = project([task()])
        self.assertFalse(release(root, "M01"))
        take(root, "M01", harness="dsh", session="agent-1")
        self.assertFalse(release(root, "M01", session="other"))
        self.assertTrue(claim_path(root).exists())
        self.assertTrue(release(root, "M01", session="agent-1"))
        self.assertIsNone(read_claim(root, "M01"))
        self.assertFalse(release(root, "M01", session="agent-1"))

    def test_beat(self):
        root = project([task()])
        with self.assertRaises(NoClaim):
            beat(root, "M01")
        write_claim(root, full_claim())
        with self.assertRaises(ClaimConflict):
            beat(root, "M01", session="other")
        claim = beat(root, "M01", session="s1")
        self.assertEqual(claim["started"], OLD)
        self.assertNotEqual(claim["heartbeat"], OLD)
        self.assertTrue(is_live(claim))

    def test_live_claims_sorted_and_stale_excluded(self):
        root = project([task()])
        take(root, "M02", harness="dsh", session="a")
        take(root, "M01", harness="claude-code", session="b")
        write_claim(root, full_claim("M03"))
        self.assertEqual([c["task"] for c in live_claims(root)], ["M01", "M02"])
        self.assertEqual([c["task"] for c in live_claims(root, ttl=0)], [])

    def test_claims_are_shared_by_all_worktrees(self):
        root = project([task()])
        worktree = root.parent / f"{root.name}-wt"
        git(root, "worktree", "add", str(worktree), "-b", "task/M01")
        try:
            take(root, "M01", harness="dsh", session="agent-1")
            self.assertEqual(claim_dir(worktree), claim_dir(root))
            self.assertEqual([c["task"] for c in live_claims(worktree)], ["M01"])
            take(worktree, "M02", harness="claude-code", session="claude-9")
            self.assertEqual([c["task"] for c in live_claims(root)], ["M01", "M02"])
        finally:
            subprocess.run(["git", "-C", str(root), "worktree", "remove", "--force", str(worktree)],
                           capture_output=True, check=False)

    def test_environment_errors(self):
        bare = project([task()], repo=False)
        with self.assertRaises(PolierError):
            take(bare, "M01", harness="cli", session="s")
        root = project([task()])
        with self.assertRaises(PolierError):
            take(root, "M01", harness="nonsense", session="s")
        with self.assertRaises(PolierError):
            take(root, "M01", harness="cli", session="")
        with self.assertRaises(PolierError):
            take(root, "../escape", harness="cli", session="s")
        self.assertIsNone(read_claim(bare, "M01"))


class Cli(unittest.TestCase):
    def test_take_list_beat_release(self):
        root = project([task()])
        taken = cli("take", "M01", "--harness", "dsh", "--session", "agent-1",
                    "--worktree", "/p/repo-M01", "--slot", "1", "--root", str(root), "--json")
        self.assertEqual(taken.returncode, 0, taken.stderr)
        claim = json.loads(taken.stdout)
        self.assertEqual((claim["task"], claim["harness"], claim["session"], claim["slot"]),
                         ("M01", "dsh", "agent-1", 1))

        listed = cli("list", "--root", str(root), "--json")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        rows = json.loads(listed.stdout)
        self.assertEqual([row["task"] for row in rows], ["M01"])
        self.assertIn("age_s", rows[0])

        human = cli("list", "--root", str(root))
        self.assertEqual(human.returncode, 0)
        self.assertIn("M01", human.stdout)
        self.assertIn("dsh", human.stdout)

        beaten = cli("beat", "M01", "--session", "agent-1", "--root", str(root), "--json")
        self.assertEqual(beaten.returncode, 0, beaten.stderr)
        self.assertEqual(json.loads(beaten.stdout)["heartbeat"], read_claim(root, "M01")["heartbeat"])

        wrong = cli("release", "M01", "--session", "other", "--root", str(root))
        self.assertEqual(wrong.returncode, 1)
        released = cli("release", "M01", "--session", "agent-1", "--root", str(root))
        self.assertEqual(released.returncode, 0, released.stderr)
        self.assertFalse(claim_path(root).exists())

    def test_conflict_is_exit_1_and_names_the_holder(self):
        root = project([task()])
        cli("take", "M01", "--harness", "dsh", "--session", "agent-1", "--root", str(root))
        conflict = cli("take", "M01", "--harness", "claude-code", "--session", "claude-9",
                       "--root", str(root))
        self.assertEqual(conflict.returncode, 1)
        self.assertIn("CLAIM CONFLICT", conflict.stderr)
        self.assertIn("agent-1", conflict.stderr)

    def test_missing_claims_are_exit_1(self):
        root = project([task()])
        self.assertEqual(cli("beat", "M01", "--root", str(root)).returncode, 1)
        self.assertEqual(cli("release", "M01", "--root", str(root)).returncode, 1)

    def test_usage_and_environment_are_exit_2(self):
        root = project([task()])
        self.assertEqual(cli("take", "M01", "--root", str(root)).returncode, 2)  # no harness/session
        self.assertEqual(cli("nonsense").returncode, 2)
        bare = project([task()], repo=False)
        self.assertEqual(cli("list", "--root", str(bare)).returncode, 2)
        self.assertIn("CLAIM ERROR", cli("list", "--root", str(bare)).stderr)

    def test_two_processes_cannot_take_the_same_task(self):
        root = project([task()])
        command = lambda session: [sys.executable, str(TOOL), "take", "M01", "--harness", "cli",
                                   "--session", session, "--root", str(root)]
        first = subprocess.Popen(command("p1"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        second = subprocess.Popen(command("p2"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out1, err1 = first.communicate(timeout=60)
        out2, err2 = second.communicate(timeout=60)
        codes = sorted([first.returncode, second.returncode])
        self.assertEqual(codes, [0, 1], (out1, err1, out2, err2))
        winner = "p1" if first.returncode == 0 else "p2"
        self.assertEqual(read_claim(root, "M01")["session"], winner)

    def test_list_in_a_worktree_shows_all_claims(self):
        root = project([task()])
        worktree = root.parent / f"{root.name}-wt"
        git(root, "worktree", "add", str(worktree), "-b", "task/M01")
        try:
            cli("take", "M01", "--harness", "dsh", "--session", "agent-1", "--root", str(root))
            listing = cli("list", "--root", str(worktree), "--json")
            self.assertEqual(listing.returncode, 0, listing.stderr)
            self.assertEqual([row["task"] for row in json.loads(listing.stdout)], ["M01"])
        finally:
            subprocess.run(["git", "-C", str(root), "worktree", "remove", "--force", str(worktree)],
                           capture_output=True, check=False)


if __name__ == "__main__":
    unittest.main()
