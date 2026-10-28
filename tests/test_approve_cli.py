"""tools/approve.py: request, grant, deny, list and check approval records."""
from __future__ import annotations

import json
import unittest

from helpers import make_project, run_tool, task


def project():
    return make_project([task("M01", status="pending")])


def run(root, *args):
    return run_tool("approve.py", *args, "--root", str(root))


def records(root):
    folder = root / "reviews" / "approvals"
    if not folder.is_dir():
        return []
    return sorted(folder.glob("AP-*.json"))


def first_id(root) -> str:
    return json.loads(records(root)[0].read_text())["id"]


class Request(unittest.TestCase):
    def test_a_request_writes_a_pending_record(self):
        root = project()
        result = run(root, "request", "--action", "new_dependency", "--task", "M01",
                     "--note", "adds httpx")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("AP-001", result.stdout)
        self.assertIn("pending", result.stdout)
        self.assertIn("requested", result.stdout)
        self.assertEqual(len(records(root)), 1)
        record = json.loads(records(root)[0].read_text())
        self.assertEqual(record["id"], "AP-001")
        self.assertEqual((record["action"], record["task"], record["status"]),
                         ("new_dependency", "M01", "pending"))
        self.assertEqual(record["requested_by"], "worker")
        self.assertEqual(record["note"], "adds httpx")
        self.assertIsNone(record["approved_by"])

    def test_an_identical_request_is_reused(self):
        root = project()
        run(root, "request", "--action", "new_dependency", "--task", "M01",
            "--note", "adds httpx")
        result = run(root, "request", "--action", "new_dependency", "--task", "M01",
                     "--note", "adds httpx")
        self.assertEqual(result.returncode, 0)
        self.assertIn("reused", result.stdout)
        self.assertEqual(len(records(root)), 1)
        self.assertEqual(first_id(root), "AP-001")

    def test_a_different_request_gets_the_next_id(self):
        root = project()
        run(root, "request", "--action", "new_dependency", "--task", "M01")
        run(root, "request", "--action", "release", "--by", "owner")
        self.assertEqual([record.name for record in records(root)],
                         ["AP-001.json", "AP-002.json"])
        self.assertIsNone(json.loads(records(root)[1].read_text())["task"])

    def test_an_unknown_action_is_a_usage_error(self):
        root = project()
        self.assertEqual(run(root, "request", "--action", "teleport").returncode, 2)

    def test_an_invalid_task_is_an_environment_error(self):
        root = project()
        result = run(root, "request", "--action", "release", "--task", "../escape")
        self.assertEqual(result.returncode, 2)


class Decide(unittest.TestCase):
    def pending(self):
        root = project()
        run(root, "request", "--action", "new_dependency", "--task", "M01",
            "--note", "adds httpx")
        return root

    def test_grant_sets_the_decision(self):
        root = self.pending()
        result = run(root, "grant", "AP-001", "--by", "owner")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("granted", result.stdout)
        record = json.loads(records(root)[0].read_text())
        self.assertEqual(record["status"], "granted")
        self.assertEqual(record["approved_by"], "owner")
        self.assertTrue(record["approved_at"])

    def test_deny_sets_the_decision(self):
        root = self.pending()
        result = run(root, "deny", "AP-001", "--by", "owner", "--note", "not in this task")
        self.assertEqual(result.returncode, 0)
        record = json.loads(records(root)[0].read_text())
        self.assertEqual(record["status"], "denied")
        self.assertEqual(record["note"], "adds httpx | not in this task")

    def test_a_decided_approval_cannot_be_decided_again(self):
        root = self.pending()
        self.assertEqual(run(root, "grant", "AP-001").returncode, 0)
        again = run(root, "grant", "AP-001")
        self.assertEqual(again.returncode, 1)
        self.assertIn("already granted", again.stderr)
        self.assertEqual(run(root, "deny", "AP-001").returncode, 1)

    def test_a_missing_approval_is_a_refusal(self):
        root = project()
        result = run(root, "grant", "AP-999")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no approval AP-999", result.stderr)

    def test_a_malformed_id_is_an_environment_error(self):
        root = project()
        for approval_id in ("AP-1", "AP-001x", "001"):
            self.assertEqual(run(root, "grant", approval_id).returncode, 2, approval_id)

    def test_the_decision_is_appended_to_the_run_record(self):
        root = self.pending()
        self.assertEqual(run(root, "grant", "AP-001", "--by", "owner").returncode, 0)
        record = json.loads((root / "runs" / "M01.json").read_text())
        event = record["events"][-1]
        self.assertEqual(event["kind"], "approval")
        self.assertEqual(event["data"], {"id": "AP-001", "action": "new_dependency",
                                         "status": "granted", "by": "owner"})


class List(unittest.TestCase):
    def test_an_empty_store_lists_nothing(self):
        root = project()
        result = run(root, "list")
        self.assertEqual(result.returncode, 0)
        self.assertIn("NO APPROVALS", result.stdout)

    def test_json_and_status_filter(self):
        root = project()
        run(root, "request", "--action", "new_dependency", "--task", "M01")
        run(root, "request", "--action", "release")
        run(root, "grant", "AP-001", "--by", "owner")
        everything = json.loads(run(root, "list", "--json").stdout)
        self.assertEqual([record["id"] for record in everything], ["AP-001", "AP-002"])
        granted = json.loads(run(root, "list", "--json", "--status", "granted").stdout)
        self.assertEqual([record["id"] for record in granted], ["AP-001"])
        self.assertIn("AP-002", run(root, "list", "--status", "pending").stdout)
        self.assertNotIn("AP-001", run(root, "list", "--status", "pending").stdout)

    def test_the_root_may_come_before_the_subcommand(self):
        root = project()
        result = run_tool("approve.py", "--root", str(root), "list", "--json")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), [])


class Check(unittest.TestCase):
    def granted(self):
        root = project()
        run(root, "request", "--action", "new_dependency", "--task", "M01")
        run(root, "grant", "AP-001", "--by", "owner")
        return root

    def test_check_exits_0_only_for_a_granted_record(self):
        root = project()
        missing = run(root, "check", "--action", "new_dependency", "--task", "M01")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("NOT GRANTED", missing.stdout)
        run(root, "request", "--action", "new_dependency", "--task", "M01")
        self.assertEqual(run(root, "check", "--action", "new_dependency",
                             "--task", "M01").returncode, 1)
        run(root, "grant", "AP-001", "--by", "owner")
        result = run(root, "check", "--action", "new_dependency", "--task", "M01")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("GRANTED", result.stdout)

    def test_check_json(self):
        root = self.granted()
        result = run(root, "check", "--action", "new_dependency", "--task", "M01", "--json")
        self.assertEqual(result.returncode, 0)
        parsed = json.loads(result.stdout)
        self.assertTrue(parsed["granted"])
        self.assertEqual(parsed["approval"]["id"], "AP-001")
        missing = run(root, "check", "--action", "release", "--json")
        self.assertEqual(missing.returncode, 1)
        self.assertFalse(json.loads(missing.stdout)["granted"])

    def test_a_record_without_a_task_matches_any_task(self):
        root = project()
        run(root, "request", "--action", "release")
        run(root, "grant", "AP-001", "--by", "owner")
        self.assertEqual(run(root, "check", "--action", "release").returncode, 0)
        self.assertEqual(run(root, "check", "--action", "release",
                             "--task", "M01").returncode, 0)

    def test_a_grant_for_another_task_does_not_match(self):
        root = project()
        run(root, "request", "--action", "scope_change", "--task", "M02")
        run(root, "grant", "AP-001", "--by", "owner")
        self.assertEqual(run(root, "check", "--action", "scope_change",
                             "--task", "M01").returncode, 1)
        self.assertEqual(run(root, "check", "--action", "scope_change",
                             "--task", "M02").returncode, 0)

    def test_an_unknown_action_is_a_usage_error(self):
        root = project()
        self.assertEqual(run(root, "check", "--action", "teleport").returncode, 2)


if __name__ == "__main__":
    unittest.main()
