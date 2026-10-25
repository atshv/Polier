"""Exclusive locks (PL-03): holder files, waiting, stale takeover."""
from __future__ import annotations

import datetime as dt
import json
import os
import socket
import subprocess
import sys
import threading
import time
import unittest

from core.errors import PolierError
from core.locks import acquire_lock, lock_path, read_lock, release_lock
from core.paths import git_common_dir

from .fixtures import project, task


def holder(task_id: str = "M01", **extra) -> dict:
    data = {
        "task": task_id,
        "slot": 1,
        "harness": "cli",
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    data.update(extra)
    return data


def write_lock(root, resource: str, data: dict):
    path = lock_path(root, resource)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class LockFile(unittest.TestCase):
    def setUp(self):
        self.root = project([task()])

    def test_path_and_safe_names(self):
        path = lock_path(self.root, "e2e")
        self.assertEqual(path, git_common_dir(self.root) / "polier" / "locks" / "e2e.lock")
        for bad in ("../x", "a/b", "", "a b", ".", ".."):
            with self.assertRaises(PolierError):
                lock_path(self.root, bad)

    def test_acquire_read_release(self):
        outcome = acquire_lock(self.root, "e2e", holder())
        self.assertTrue(outcome["acquired"])
        self.assertEqual(outcome["waited"], 0.0)
        self.assertFalse(outcome["taken_over"])
        self.assertIsNone(outcome["warning"])
        self.assertEqual(outcome["holder"]["task"], "M01")

        stored = read_lock(self.root, "e2e")
        self.assertEqual(stored["task"], "M01")
        self.assertEqual(stored["harness"], "cli")
        self.assertEqual(stored["pid"], os.getpid())
        self.assertEqual(stored["host"], socket.gethostname())
        self.assertIn("started", stored)

        self.assertTrue(release_lock(self.root, "e2e"))
        self.assertIsNone(read_lock(self.root, "e2e"))
        self.assertFalse(release_lock(self.root, "e2e"))

    def test_holder_defaults_are_filled_in(self):
        # The gate passes all keys; the lock fills whatever a caller leaves out.
        outcome = acquire_lock(self.root, "e2e", {"task": "M02", "harness": "dsh"}, wait=0)
        self.assertEqual(outcome["holder"]["pid"], os.getpid())
        self.assertEqual(outcome["holder"]["host"], socket.gethostname())
        self.assertIsNotNone(outcome["holder"]["started"])


class Waiting(unittest.TestCase):
    def setUp(self):
        self.root = project([task()])

    def tearDown(self):
        release_lock(self.root, "e2e")

    def test_live_lock_ends_in_a_busy_result(self):
        acquire_lock(self.root, "e2e", holder("M01"), wait=0)
        second = acquire_lock(self.root, "e2e", holder("M02"), wait=0.12, poll=0.02)
        self.assertFalse(second["acquired"])
        self.assertGreaterEqual(second["waited"], 0.1)
        self.assertEqual(second["holder"]["task"], "M01")
        self.assertFalse(second["taken_over"])
        self.assertIsNone(second["warning"])

    def test_waits_until_the_holder_releases(self):
        acquire_lock(self.root, "e2e", holder("M01"), wait=0)
        seen = []

        def release_later():
            time.sleep(0.2)
            release_lock(self.root, "e2e")

        thread = threading.Thread(target=release_later, daemon=True)
        thread.start()
        second = acquire_lock(self.root, "e2e", holder("M02"), wait=3.0, poll=0.02,
                              on_wait=lambda current, waited: seen.append((current, waited)))
        thread.join(timeout=5)
        self.assertTrue(second["acquired"])
        self.assertGreaterEqual(second["waited"], 0.1)
        self.assertEqual(second["holder"]["task"], "M02")
        self.assertTrue(seen)
        self.assertIn("M01", [current["task"] for current, _ in seen if isinstance(current, dict)])
        self.assertTrue(any(waited > 0 for _, waited in seen))


class Stale(unittest.TestCase):
    def setUp(self):
        self.root = project([task()])

    def test_dead_pid_is_taken_over_with_a_warning(self):
        process = subprocess.Popen([sys.executable, "-c", "pass"])
        process.wait()
        write_lock(self.root, "e2e", holder("old", pid=process.pid))

        outcome = acquire_lock(self.root, "e2e", holder("new"), wait=0.5, ttl=3600)
        self.assertTrue(outcome["acquired"])
        self.assertTrue(outcome["taken_over"])
        self.assertIn("stale", outcome["warning"])
        self.assertIn("gone", outcome["warning"])
        self.assertEqual(read_lock(self.root, "e2e")["task"], "new")

    def test_old_lock_is_taken_over_even_when_the_pid_is_alive(self):
        old = (dt.datetime.now(dt.timezone.utc)
               - dt.timedelta(hours=2)).isoformat(timespec="seconds")
        write_lock(self.root, "e2e", holder("old", started=old))

        outcome = acquire_lock(self.root, "e2e", holder("new"), wait=0.5, ttl=60)
        self.assertTrue(outcome["acquired"])
        self.assertTrue(outcome["taken_over"])
        self.assertIn("ttl", outcome["warning"])
        self.assertEqual(read_lock(self.root, "e2e")["task"], "new")

    def test_fresh_live_lock_is_not_taken_over(self):
        write_lock(self.root, "e2e", holder("old"))
        outcome = acquire_lock(self.root, "e2e", holder("new"), wait=0.05, poll=0.01)
        self.assertFalse(outcome["acquired"])
        self.assertFalse(outcome["taken_over"])
        self.assertEqual(read_lock(self.root, "e2e")["task"], "old")

    def test_recent_empty_lock_file_is_not_stolen(self):
        path = write_lock(self.root, "e2e", {})
        path.write_text("", encoding="utf-8")
        outcome = acquire_lock(self.root, "e2e", holder("new"), wait=0.05, poll=0.01)
        self.assertFalse(outcome["acquired"])

        stamp = time.time() - 3600
        os.utime(str(path), (stamp, stamp))
        outcome = acquire_lock(self.root, "e2e", holder("new"), wait=0.2, poll=0.01)
        self.assertTrue(outcome["acquired"])
        self.assertTrue(outcome["taken_over"])
        self.assertIn("unreadable", outcome["warning"])


if __name__ == "__main__":
    unittest.main()
