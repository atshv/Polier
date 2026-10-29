"""core/inbox.py: Your Work and the inbox with read state."""
from __future__ import annotations

import unittest

from dash_helpers import sample_project

from core import approvals, inbox, plan_edit, settings


class InboxTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_project()

    def test_your_work_counts(self) -> None:
        plan_edit.update_task(self.root, "ENG-01", {"owner": "owner"})
        result = inbox.your_work(self.root)
        self.assertEqual(result["me"], "owner")
        self.assertEqual(result["counts"]["mine"], 1)
        self.assertGreaterEqual(result["counts"]["reviews"], 0)
        self.assertTrue(any(item["id"] == "ENG-01" for item in result["mine"]))

    def test_approval_and_read_state(self) -> None:
        approvals.request(self.root, "new_dependency", "ENG-01", by="lead", note="needs a package")
        items = inbox.inbox(self.root)
        self.assertTrue(items)
        approval_item = next(item for item in items if item["kind"] == "approval")
        self.assertFalse(approval_item["read"])
        inbox.mark_read(self.root, [approval_item["id"]])
        items = inbox.inbox(self.root)
        approval_item = next(item for item in items if item["kind"] == "approval")
        self.assertTrue(approval_item["read"])
        summary = inbox.inbox_summary(self.root)
        self.assertGreaterEqual(summary["counts"]["total"], 1)
        self.assertGreaterEqual(summary["counts"]["unread"], 0)

    def test_read_all_and_reset(self) -> None:
        approvals.request(self.root, "new_dependency", "ENG-01", by="lead", note="x")
        state = inbox.mark_read(self.root, all_items=True)
        self.assertGreaterEqual(len(state["read"]), 1)
        self.assertEqual(inbox.inbox_summary(self.root)["counts"]["unread"], 0)
        cleared = inbox.mark_read(self.root, reset=True)
        self.assertEqual(cleared["read"], {})

    def test_identity_uses_settings(self) -> None:
        settings.save(self.root, {"defaults": {"me": "rasul"}})
        self.assertEqual(inbox.identity(self.root)["me"], "rasul")


if __name__ == "__main__":
    unittest.main()
