"""core.runs: runs/<ID>.json, attempts and events (PL-19)."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from core import runs
from core.errors import PolierError

from .fixtures import project, task, write_policy

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")


class Storage(unittest.TestCase):
    def test_run_path(self):
        root = project([task()], repo=False)
        self.assertEqual(runs.run_path(root, "M01"), root / "runs" / "M01.json")

    def test_invalid_task_ids(self):
        root = project([task()], repo=False)
        for bad in ("", "  ", ".", "..", "../wrap", "M01/x", "M01\\x", None):
            with self.subTest(bad):
                with self.assertRaises(PolierError):
                    runs.run_path(root, bad)

    def test_missing_file_gives_an_empty_skeleton(self):
        root = project([task()], repo=False)
        skeleton = runs.load_run(root, "M01")
        self.assertEqual(skeleton, {"task": "M01", "state": "idle", "attempt": 0,
                                    "attempts": [], "events": [], "usage": {}, "updated": None})
        self.assertFalse(runs.run_path(root, "M01").exists())
        self.assertFalse(runs.enabled(root))

    def test_broken_file_never_stops_the_reader(self):
        root = project([task()], repo=False)
        path = runs.run_path(root, "M01")
        path.parent.mkdir(parents=True)
        for broken in ("{not json", "[]", '"text"', ""):
            with self.subTest(broken):
                path.write_text(broken, encoding="utf-8")
                self.assertEqual(runs.load_run(root, "M01")["state"], "idle")
                self.assertEqual(runs.load_run(root, "M01")["attempt"], 0)

    def test_unreadable_fields_are_normalized(self):
        root = project([task()], repo=False)
        path = runs.run_path(root, "M01")
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({
            "task": "M01", "state": "nonsense", "attempt": "two",
            "attempts": [{"n": 1, "result": "maybe", "note": 5}, "junk"],
            "events": [{"kind": "gate"}, "junk", {"at": "x", "kind": "", "data": []}],
            "updated": 4,
        }), encoding="utf-8")
        record = runs.load_run(root, "M01")
        self.assertEqual(record["state"], "idle")
        self.assertEqual(record["attempt"], 2)              # max(attempt, len(attempts))
        self.assertEqual(record["attempts"][0]["result"], None)
        self.assertEqual(record["attempts"][1]["n"], 2)
        self.assertEqual(len(record["events"]), 2)          # the string entry is dropped
        self.assertEqual(record["events"][0]["kind"], "gate")
        self.assertEqual(record["events"][1]["kind"], "note")
        self.assertIsNone(record["updated"])

    def test_the_stored_task_id_is_used(self):
        root = project([task()], repo=False)
        path = runs.run_path(root, "M01")
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"task": "M02", "state": "running"}), encoding="utf-8")
        self.assertEqual(runs.load_run(root, "M01")["task"], "M02")


class Attempts(unittest.TestCase):
    def test_start_attempt(self):
        root = project([task()], repo=False)
        record = runs.start_attempt(root, "M01", actor="lead")
        self.assertEqual((record["state"], record["attempt"]), ("running", 1))
        self.assertEqual(record["attempts"][0]["n"], 1)
        self.assertIsNone(record["attempts"][0]["ended"])
        self.assertTrue(ISO.match(record["attempts"][0]["started"]))
        self.assertTrue(ISO.match(record["updated"]))
        start = record["events"][-1]
        self.assertEqual((start["kind"], start["data"]), ("start", {"actor": "lead"}))
        self.assertEqual(runs.run_state(root, "M01"), "running")
        self.assertEqual(runs.attempt_count(root, "M01"), 1)

    def test_finish_attempt_closes_the_open_one(self):
        root = project([task()], repo=False)
        runs.start_attempt(root, "M01")
        runs.start_attempt(root, "M01")
        record = runs.finish_attempt(root, "M01", "fail", note="two blockers")
        self.assertEqual(record["state"], "failed")
        self.assertEqual(len(record["attempts"]), 2)
        closed = record["attempts"][-1]
        self.assertEqual((closed["result"], closed["note"]), ("fail", "two blockers"))
        self.assertTrue(ISO.match(closed["ended"]))
        self.assertIsNone(record["attempts"][0]["ended"])

    def test_state_per_result(self):
        for result, expected in (("pass", "done"), ("fail", "failed"),
                                 ("cancelled", "blocked")):
            root = project([task()], repo=False)
            runs.start_attempt(root, "M01")
            self.assertEqual(runs.finish_attempt(root, "M01", result)["state"], expected)

    def test_finish_without_an_open_attempt_does_not_raise(self):
        root = project([task()], repo=False)
        record = runs.finish_attempt(root, "M01", "pass")
        self.assertEqual(record["attempts"], [])
        self.assertEqual(record["state"], "done")

    def test_unknown_result_is_an_error(self):
        root = project([task()], repo=False)
        with self.assertRaises(PolierError):
            runs.finish_attempt(root, "M01", "maybe")

    def test_exhausted(self):
        root = project([task()], repo=False)
        runs.start_attempt(root, "M01")
        self.assertFalse(runs.exhausted(root, "M01", 2))
        runs.start_attempt(root, "M01")
        self.assertTrue(runs.exhausted(root, "M01", 2))
        runs.finish_attempt(root, "M01", "pass")
        self.assertFalse(runs.exhausted(root, "M01", 2))
        self.assertFalse(runs.exhausted(root, "M01", "2"))


class Events(unittest.TestCase):
    def test_append_event_and_last_event(self):
        root = project([task()], repo=False)
        self.assertIsNone(runs.last_event(root, "M01"))
        payload = {"gate": "tests", "result": "pass", "record": "reviews/evidence/x.json"}
        record = runs.append_event(root, "M01", "gate", payload)
        self.assertEqual(record["events"], [{"at": record["updated"], "kind": "gate",
                                             "data": payload}])
        self.assertEqual(runs.last_event(root, "M01"), record["events"][0])
        self.assertTrue(ISO.match(record["updated"]))

    def test_explicit_timestamp(self):
        root = project([task()], repo=False)
        when = "2026-01-02T03:04:05+00:00"
        record = runs.append_event(root, "M01", "note", {"text": "x"}, at=when)
        self.assertEqual(record["updated"], when)
        self.assertEqual(record["events"][0]["at"], when)

    def test_the_last_500_events_are_kept(self):
        root = project([task()], repo=False)
        for index in range(runs.MAX_EVENTS + 5):
            runs.append_event(root, "M01", "note", {"n": index})
        record = runs.load_run(root, "M01")
        self.assertEqual(len(record["events"]), runs.MAX_EVENTS)
        self.assertEqual(record["events"][-1]["data"], {"n": runs.MAX_EVENTS + 4})
        self.assertEqual(record["events"][0]["data"], {"n": 5})

    def test_a_corrupt_file_is_replaced_by_a_valid_one(self):
        root = project([task()], repo=False)
        path = runs.run_path(root, "M01")
        path.parent.mkdir(parents=True)
        path.write_text("{broken", encoding="utf-8")
        record = runs.append_event(root, "M01", "note", {"text": "after the crash"})
        self.assertEqual(record["task"], "M01")
        self.assertEqual(len(record["events"]), 1)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["events"],
                         record["events"])


class RecordGate(unittest.TestCase):
    def test_nothing_is_written_without_a_policy(self):
        root = project([task()], repo=False)
        self.assertIsNone(runs.record_gate(root, "M01", "tests", "pass",
                                           "reviews/evidence/x.json"))
        self.assertFalse(runs.run_path(root, "M01").exists())

    def test_a_gate_event_is_appended_with_a_policy(self):
        root = project([task()], repo=False)
        write_policy(root)
        self.assertTrue(runs.enabled(root))
        runs.record_gate(root, "M01", "tests", "pass", "reviews/evidence/x.json")
        event = runs.last_event(root, "M01")
        self.assertEqual(event["kind"], "gate")
        self.assertEqual(event["data"], {"gate": "tests", "result": "pass",
                                         "record": "reviews/evidence/x.json"})

    def test_never_raises(self):
        root = project([task()], repo=False)
        write_policy(root)
        runs_path = root / "runs"
        runs_path.write_text("this is a file, not a folder", encoding="utf-8")
        self.assertIsNone(runs.record_gate(root, "M01", "tests", "pass", "x.json"))
        (root / "policy.json").write_text("{broken", encoding="utf-8")
        self.assertIsNone(runs.record_gate(root, "M01", "tests", "pass", "x.json"))
        self.assertIsNone(runs.record_gate(root, "M01/../x", "tests", "pass", "x.json"))


class Summary(unittest.TestCase):
    def test_summary_condenses_the_record(self):
        root = project([task()], repo=False)
        runs.start_attempt(root, "M01", actor="lead")
        summary = runs.summary(root, "M01")
        self.assertEqual(summary["task"], "M01")
        self.assertEqual((summary["state"], summary["attempt"]), ("running", 1))
        self.assertEqual(len(summary["attempts"]), 1)
        self.assertEqual(summary["last_event"]["kind"], "start")
        self.assertTrue(ISO.match(summary["updated"]))

    def test_summary_of_a_missing_record_is_empty(self):
        root = project([task()], repo=False)
        summary = runs.summary(root, "M01")
        self.assertEqual((summary["state"], summary["attempt"], summary["last_event"]),
                         ("idle", 0, None))


class AtomicWrites(unittest.TestCase):
    def test_no_temp_file_and_no_lock_after_a_write(self):
        root = project([task()], repo=False)
        runs.start_attempt(root, "M01")
        folder = root / "runs"
        self.assertEqual(sorted(path.name for path in folder.iterdir()), ["M01.json"])
        self.assertFalse(any(path.name.endswith(".tmp") for path in folder.iterdir()))
        self.assertFalse(any(path.name.endswith(".lock") for path in folder.iterdir()))
        json.loads((folder / "M01.json").read_text(encoding="utf-8"))

    def test_the_runs_folder_is_created(self):
        root = project([task()], repo=False)
        self.assertFalse((root / "runs").exists())
        runs.start_attempt(root, "M01")
        self.assertTrue((root / "runs" / "M01.json").is_file())


if __name__ == "__main__":
    unittest.main()
