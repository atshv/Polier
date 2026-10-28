"""tools/gate.py appends a ``gate`` event to runs/<ID>.json (1.1), for every written record.

The run record is the execution trail: a pass, a failure, a timeout, an
infrastructure result and a busy resource all leave a gate event, and a broken
runs/ store never changes the gate result or its evidence record.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import unittest
from pathlib import Path

from helpers import make_project, run_tool, task

from core.locks import acquire_lock, release_lock

PY = [sys.executable, "-c"]


def write_policy(root: Path, **limits) -> None:
    """A minimal valid policy.json: the defaults are filled in by core.policy."""
    policy: dict = {"version": 1}
    if limits:
        policy["limits"] = limits
    (root / "policy.json").write_text(json.dumps(policy), encoding="utf-8")


def gate(root: Path, *args: str):
    return run_tool("gate.py", "--root", str(root), *args)


def events(root: Path, tid: str = "M01") -> list:
    return json.loads((root / "runs" / f"{tid}.json").read_text(encoding="utf-8"))["events"]


class GateRunEvent(unittest.TestCase):
    def test_a_passing_gate_appends_a_run_event(self):
        root = make_project([task()])
        write_policy(root)
        result = gate(root, "--task", "M01", "--name", "tests", "--", *PY, "print('ok')")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((root / "runs" / "M01.json").is_file())

        data = json.loads((root / "runs" / "M01.json").read_text(encoding="utf-8"))
        self.assertEqual(data["task"], "M01")
        self.assertEqual(data["state"], "idle")
        gate_events = [event for event in data["events"] if event["kind"] == "gate"]
        self.assertEqual(len(gate_events), 1, data["events"])
        payload = gate_events[0]["data"]
        self.assertEqual((payload["gate"], payload["result"]), ("tests", "pass"))
        record = payload["record"]
        self.assertTrue(record.startswith("reviews/evidence/M01-tests-"), record)
        self.assertTrue((root / record).is_file())
        self.assertIn(record, result.stdout)

    def test_a_failing_gate_appends_a_run_event_after_the_record(self):
        root = make_project([task()])
        write_policy(root)
        result = gate(root, "--task", "M01", "--name", "tests", "--", *PY,
                      "raise SystemExit(3)")
        self.assertEqual(result.returncode, 3)
        event = events(root)[-1]
        self.assertEqual((event["kind"], event["data"]["result"]), ("gate", "fail"))
        self.assertTrue((root / event["data"]["record"]).is_file())

    def test_a_busy_gate_appends_a_run_event_and_keeps_exit_75(self):
        root = make_project([task()])
        write_policy(root)
        holder = {
            "task": "other", "slot": 1, "harness": "dsh", "pid": 1, "host": "elsewhere",
            "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        }
        acquire_lock(root, "e2e", holder)
        try:
            result = gate(root, "--task", "M01", "--name", "e2e",
                          "--exclusive", "e2e", "--lock-wait", "0.2", "--", *PY, "pass")
        finally:
            release_lock(root, "e2e")
        self.assertEqual(result.returncode, 75, result.stderr)
        event = events(root)[-1]
        self.assertEqual((event["kind"], event["data"]["result"]), ("gate", "busy"))
        self.assertIn("BUSY", result.stdout)

    def test_without_a_policy_no_run_record_is_created(self):
        root = make_project([task()])
        result = gate(root, "--task", "M01", "--name", "tests", "--", *PY, "print('ok')")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((root / "runs").exists())

    def test_a_broken_runs_store_does_not_change_the_gate_result(self):
        root = make_project([task()])
        write_policy(root)
        (root / "runs").write_text("not a folder\n", encoding="utf-8")
        result = gate(root, "--task", "M01", "--name", "tests", "--", *PY, "print('ok')")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GATE tests: PASS", result.stdout)
        self.assertTrue((root / "runs").is_file())
        self.assertTrue(any((root / "reviews" / "evidence").glob("M01-tests-*.json")))


if __name__ == "__main__":
    unittest.main()
