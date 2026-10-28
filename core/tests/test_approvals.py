"""core.approvals: reviews/approvals/AP-NNN.json, the human decisions (PL-21)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from core import approvals
from core.errors import PolierError

from .fixtures import project, task, write_json

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")
PACKAGE = Path(__file__).resolve().parents[2]


def store(root: Path) -> Path:
    return root / "reviews" / "approvals"


class Requesting(unittest.TestCase):
    def test_request_writes_ap_001(self):
        root = project([task()], repo=False)
        record = approvals.request(root, "new_dependency", "M01", by="worker",
                                   note="adds httpx 0.27")
        self.assertEqual(record["id"], "AP-001")
        self.assertEqual(record["action"], "new_dependency")
        self.assertEqual(record["task"], "M01")
        self.assertEqual(record["status"], "pending")
        self.assertEqual(record["requested_by"], "worker")
        self.assertTrue(ISO.match(record["requested_at"]))
        self.assertIsNone(record["approved_by"])
        self.assertIsNone(record["approved_at"])
        self.assertEqual(record["note"], "adds httpx 0.27")
        stored = json.loads((store(root) / "AP-001.json").read_text(encoding="utf-8"))
        self.assertEqual(stored, record)

    def test_ids_increase_and_load_all_is_sorted(self):
        root = project([task()], repo=False)
        first = approvals.request(root, "new_dependency", "M01", note="one")
        second = approvals.request(root, "new_dependency", "M02", note="two")
        third = approvals.request(root, "release", note="three")
        self.assertEqual([first["id"], second["id"], third["id"]],
                         ["AP-001", "AP-002", "AP-003"])
        self.assertEqual([row["id"] for row in approvals.load_all(root)],
                         ["AP-001", "AP-002", "AP-003"])
        self.assertEqual(approvals.get(root, "AP-002"), second)
        self.assertIsNone(approvals.get(root, "AP-404"))

    def test_an_identical_pending_request_is_reused(self):
        root = project([task()], repo=False)
        first = approvals.request(root, "new_dependency", "M01", by="worker", note="adds x")
        again = approvals.request(root, "new_dependency", "M01", by="worker", note="adds x")
        self.assertEqual(again["id"], first["id"])
        self.assertEqual(len(approvals.load_all(root)), 1)
        other = approvals.request(root, "new_dependency", "M01", by="worker", note="adds y")
        self.assertEqual(other["id"], "AP-002")
        other_requester = approvals.request(root, "new_dependency", "M01", by="reviewer",
                                            note="adds x")
        self.assertEqual(other_requester["id"], "AP-003")
        decided = approvals.request(root, "release", note="ship it")
        approvals.grant(root, decided["id"], "owner")
        new = approvals.request(root, "release", note="ship it")
        self.assertNotEqual(new["id"], decided["id"], "a decided request is not reused")

    def test_task_is_optional(self):
        root = project([task()], repo=False)
        record = approvals.request(root, "release", by="lead", note="v1.1.0")
        self.assertIsNone(record["task"])

    def test_invalid_input(self):
        root = project([task()], repo=False)
        with self.assertRaises(PolierError):
            approvals.request(root, "teleport", "M01")
        with self.assertRaises(PolierError):
            approvals.request(root, "", "M01")
        with self.assertRaises(PolierError):
            approvals.request(root, "release", "M01", by="")
        with self.assertRaises(PolierError):
            approvals.request(root, "release", "../escape")
        self.assertFalse(store(root).exists())

    def test_invalid_ids_are_rejected_on_read(self):
        self.assertFalse(approvals.valid_id("AP-1"))
        self.assertFalse(approvals.valid_id("AP-001x"))
        self.assertFalse(approvals.valid_id("AP-"))
        self.assertFalse(approvals.valid_id(None))
        self.assertTrue(approvals.valid_id("AP-001"))
        self.assertTrue(approvals.valid_id("AP-1234"))
        root = project([task()], repo=False)
        self.assertIsNone(approvals.get(root, "AP-1"))
        self.assertIsNone(approvals.get(root, None))

    def test_two_processes_get_different_ids(self):
        root = project([task()], repo=False)
        script = (
            "import sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from core.approvals import request\n"
            "print(request(sys.argv[2], 'release', 'M01', by='worker', note=sys.argv[3])['id'])\n"
        )
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", script, str(PACKAGE), str(root), f"note {index}"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for index in range(4)
        ]
        results = [process.communicate(timeout=120) for process in processes]
        self.assertEqual([process.returncode for process in processes], [0, 0, 0, 0],
                         results)
        ids = [out.strip() for out, _err in results]
        self.assertEqual(sorted(ids), ["AP-001", "AP-002", "AP-003", "AP-004"])


class Deciding(unittest.TestCase):
    def test_grant(self):
        root = project([task()], repo=False)
        record = approvals.request(root, "new_dependency", "M01", note="adds httpx")
        granted = approvals.grant(root, record["id"], "owner", note="approved")
        self.assertEqual(granted["status"], "granted")
        self.assertEqual(granted["approved_by"], "owner")
        self.assertTrue(ISO.match(granted["approved_at"]))
        self.assertEqual(granted["note"], "adds httpx | approved")
        self.assertEqual(approvals.get(root, record["id"])["status"], "granted")
        with self.assertRaises(PolierError):
            approvals.grant(root, record["id"], "owner")

    def test_deny_and_second_decision(self):
        root = project([task()], repo=False)
        record = approvals.request(root, "scope_change", "M01", note="widen the scope")
        denied = approvals.deny(root, record["id"], "owner", note="too wide")
        self.assertEqual(denied["status"], "denied")
        self.assertEqual(denied["note"], "widen the scope | too wide")
        with self.assertRaises(PolierError):
            approvals.deny(root, record["id"], "owner")

    def test_missing_and_invalid_records(self):
        root = project([task()], repo=False)
        with self.assertRaises(PolierError):
            approvals.grant(root, "AP-999", "owner")
        with self.assertRaises(PolierError):
            approvals.grant(root, "AP-1", "owner")
        record = approvals.request(root, "release", note="go")
        with self.assertRaises(PolierError):
            approvals.grant(root, record["id"], "")

    def test_grant_appends_a_run_event_when_the_task_is_known(self):
        root = project([task()], repo=False)
        from core.runs import load_run
        record = approvals.request(root, "new_dependency", "M01", note="adds httpx")
        approvals.grant(root, record["id"], "owner")
        events = [event for event in load_run(root, "M01")["events"]
                  if event["kind"] == "approval"]
        self.assertEqual(events[0]["data"], {
            "id": record["id"], "action": "new_dependency", "status": "granted",
            "by": "owner"})
        denied = approvals.request(root, "scope_change", "M01", note="widen")
        approvals.deny(root, denied["id"], "owner")
        events = [event for event in load_run(root, "M01")["events"]
                  if event["kind"] == "approval"]
        self.assertEqual(events[-1]["data"]["status"], "denied")

    def test_a_global_approval_writes_no_run_record(self):
        root = project([task()], repo=False)
        record = approvals.request(root, "release", note="v1.1.0")
        approvals.grant(root, record["id"], "owner")
        self.assertFalse((root / "runs").exists())

    def test_grant_does_not_fail_when_the_run_store_is_broken(self):
        root = project([task()], repo=False)
        (root / "runs").write_text("not a folder", encoding="utf-8")
        record = approvals.request(root, "new_dependency", "M01", note="adds x")
        granted = approvals.grant(root, record["id"], "owner")
        self.assertEqual(granted["status"], "granted")


class Lookup(unittest.TestCase):
    def test_granted_newest_and_task_matching(self):
        root = project([task()], repo=False)
        first = approvals.request(root, "merge_to_base", "M01", note="one")
        approvals.grant(root, first["id"], "owner")
        self.assertTrue(approvals.has_grant(root, "merge_to_base", "M01"))
        self.assertFalse(approvals.has_grant(root, "merge_to_base", "M02"))
        second = approvals.request(root, "merge_to_base", "M01", note="two")
        approvals.grant(root, second["id"], "owner")
        self.assertEqual(approvals.granted(root, "merge_to_base", "M01")["id"], second["id"])
        self.assertIsNone(approvals.granted(root, "release"))
        self.assertIsNone(approvals.granted(root, "teleport"))

    def test_a_global_grant_matches_every_task(self):
        root = project([task()], repo=False)
        record = approvals.request(root, "release", note="v1.1.0")
        approvals.grant(root, record["id"], "owner")
        self.assertTrue(approvals.has_grant(root, "release"))
        self.assertTrue(approvals.has_grant(root, "release", "M01"))
        self.assertTrue(approvals.has_grant(root, "release", "M99"))
        self.assertEqual(approvals.granted(root, "release", "M01")["id"], record["id"])

    def test_pending(self):
        root = project([task(), task("M02")], repo=False)
        one = approvals.request(root, "new_dependency", "M01", note="one")
        approvals.request(root, "release", note="global")
        approvals.request(root, "scope_change", "M02", note="two")
        self.assertEqual([row["id"] for row in approvals.pending(root)],
                         ["AP-001", "AP-002", "AP-003"])
        self.assertEqual([row["id"] for row in approvals.pending(root, "M01")],
                         ["AP-001", "AP-002"])   # the global one concerns M01 as well
        self.assertEqual([row["id"] for row in approvals.pending(root, "M02")],
                         ["AP-002", "AP-003"])
        approvals.grant(root, one["id"], "owner")
        self.assertEqual([row["id"] for row in approvals.pending(root)], ["AP-002", "AP-003"])


class Validation(unittest.TestCase):
    def test_a_clean_store_has_no_errors(self):
        root = project([task()], repo=False)
        record = approvals.request(root, "new_dependency", "M01", note="x")
        approvals.grant(root, record["id"], "owner")
        board = json.loads((root / "board.json").read_text(encoding="utf-8"))
        self.assertEqual(approvals.errors(root, board), [])
        self.assertEqual(approvals.errors(root), [])

    def test_every_problem_is_reported(self):
        root = project([task()], repo=False)
        store(root).mkdir(parents=True)
        (store(root) / "AP-001.json").write_text("{broken", encoding="utf-8")
        write_json(store(root) / "AP-002.json", {
            "id": "AP-999", "action": "new_dependency", "task": "M01",
            "status": "pending", "requested_by": "worker",
            "requested_at": "2026-01-01T00:00:00+00:00"})
        write_json(store(root) / "AP-003.json", {
            "id": "AP-003", "action": "teleport", "task": "M99",
            "status": "maybe", "requested_by": "", "requested_at": "yesterday"})
        write_json(store(root) / "AP-004.json", {
            "id": "AP-004", "action": "release", "task": None,
            "status": "granted", "requested_by": "lead",
            "requested_at": "2026-01-01T00:00:00+00:00"})
        write_json(store(root) / "AP-4.json", {"id": "AP-4", "status": "pending"})
        board = {"tasks": [task()]}
        problems = approvals.errors(root, board)
        text = "\n".join(problems)
        self.assertTrue(any("AP-001.json: is not a JSON object" in p for p in problems),
                        problems)
        self.assertIn("AP-002.json: id 'AP-999' does not match the file name", text)
        self.assertIn("unknown status 'maybe'", text)
        self.assertIn("unknown action 'teleport'", text)
        self.assertIn("unknown task 'M99'", text)
        self.assertIn("requested_by is missing", text)
        self.assertIn("requested_at is not an ISO 8601 timestamp", text)
        self.assertIn("a granted record needs approved_by", text)
        self.assertIn("a granted record needs approved_at", text)
        self.assertIn("id must be AP- plus at least 3 digits", text)

    def test_an_unknown_task_is_only_checked_with_a_board(self):
        root = project([task()], repo=False)
        write_json(store(root) / "AP-001.json", {
            "id": "AP-001", "action": "release", "task": "M99",
            "status": "pending", "requested_by": "lead",
            "requested_at": "2026-01-01T00:00:00+00:00"})
        self.assertEqual(approvals.errors(root), [])
        self.assertTrue(approvals.errors(root, {"tasks": [task()]}))

    def test_load_all_skips_broken_files(self):
        root = project([task()], repo=False)
        store(root).mkdir(parents=True)
        (store(root) / "AP-001.json").write_text("{broken", encoding="utf-8")
        write_json(store(root) / "AP-002.json", {
            "id": "AP-002", "action": "release", "status": "pending",
            "requested_by": "lead", "requested_at": "2026-01-01T00:00:00+00:00"})
        self.assertEqual([row["id"] for row in approvals.load_all(root)], ["AP-002"])

    def test_writes_leave_no_temporary_files(self):
        root = project([task()], repo=False)
        record = approvals.request(root, "release", note="go")
        approvals.grant(root, record["id"], "owner")
        names = sorted(path.name for path in store(root).iterdir())
        self.assertEqual(names, ["AP-001.json"])
        self.assertFalse(any(name.endswith(".tmp") for name in names))
        self.assertFalse(any(name.endswith(".lock") for name in names))


if __name__ == "__main__":
    unittest.main()
