"""core/jobs.py: streaming gate/check/audit jobs and their records."""
from __future__ import annotations

import glob
import time
import unittest

from dash_helpers import PACKAGE, sample_project

from core import runs
from core.jobs import JobManager


def wait(manager: JobManager, job_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        view = manager.get(job_id)
        if view["status"] not in ("running", "starting"):
            return view
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish")


class JobManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_project()
        self.manager = JobManager(self.root, package_root=PACKAGE)

    def test_gate_job_writes_a_passing_record_and_run_event(self) -> None:
        job = self.manager.start_gate("F-01", "smoke", "echo hello")
        done = wait(self.manager, job["id"])
        self.assertEqual(done["status"], "pass", done)
        self.assertIn("hello", self.manager.log(job["id"])["text"])
        records = glob.glob(str(self.root / "reviews" / "evidence" / "F-01-smoke-*.json"))
        self.assertTrue(records)
        events = runs.load_run(self.root, "F-01")["events"]
        self.assertTrue(any(event["kind"] == "gate" and event["data"].get("gate") == "smoke"
                            for event in events))

    def test_failing_gate_is_recorded_as_fail(self) -> None:
        job = self.manager.start_gate("F-01", "smoke", "exit 3")
        done = wait(self.manager, job["id"])
        self.assertEqual(done["status"], "fail")
        self.assertEqual(done["exit_code"], 3)
        records = glob.glob(str(self.root / "reviews" / "evidence" / "F-01-smoke-*.json"))
        self.assertTrue(records)

    def test_stop_terminates_the_gate(self) -> None:
        job = self.manager.start_gate("F-01", "smoke", "sleep 30")
        deadline = time.time() + 10
        while time.time() < deadline and not self.manager.get(job["id"])["pid"]:
            time.sleep(0.05)
        self.manager.stop(job["id"])
        done = wait(self.manager, job["id"], timeout=15)
        self.assertIn(done["status"], ("fail", "stopped"))
        self.assertIn("stopped by the operator", self.manager.log(job["id"])["text"])

    def test_check_and_audit_jobs_finish(self) -> None:
        check = self.manager.start_check()
        done = wait(self.manager, check["id"], timeout=120)
        self.assertIn(done["status"], ("pass", "fail"))
        self.assertTrue(self.manager.log(check["id"])["text"].strip())
        audit = self.manager.start_audit()
        done = wait(self.manager, audit["id"], timeout=120)
        self.assertIn(done["status"], ("pass", "fail"))
        self.assertIn("audit", self.manager.log(audit["id"])["text"])


if __name__ == "__main__":
    unittest.main()
