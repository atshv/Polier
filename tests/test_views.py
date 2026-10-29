"""core/views.py: saved views stored as committed JSON files."""
from __future__ import annotations

import tempfile
import unittest

from core import filters, views
from core.errors import PolierError

VIEW = {"id": "review-queue", "name": "Review queue", "kind": "table",
        "filters": [{"field": "status", "op": "any_of", "value": ["review", "verifying"]}],
        "group_by": "owner", "sort": {"field": "id", "dir": "asc"},
        "columns": ["title", "status", "owner"], "created_by": "owner"}


class ViewsTest(unittest.TestCase):
    def test_save_list_delete(self) -> None:
        root = tempfile.mkdtemp(prefix="pl-views-")
        saved = views.save(root, VIEW)
        self.assertEqual(saved["id"], "review-queue")
        self.assertTrue((__import__("pathlib").Path(root) / "views" / "review-queue.json").is_file())
        self.assertEqual([view["id"] for view in views.load_all(root)], ["review-queue"])
        self.assertEqual(views.delete(root, "review-queue")["deleted"], True)
        self.assertEqual(views.load_all(root), [])
        with self.assertRaises(KeyError):
            views.delete(root, "review-queue")

    def test_validation(self) -> None:
        root = tempfile.mkdtemp(prefix="pl-views-")
        with self.assertRaises(PolierError):
            views.save(root, {**VIEW, "id": "Bad"})
        with self.assertRaises(PolierError):
            views.save(root, {**VIEW, "filters": [{"field": "status", "op": "is", "value": "nope"}]})
        with self.assertRaises(PolierError):
            views.save(root, {**VIEW, "group_by": "nope"})
        with self.assertRaises(PolierError):
            views.save(root, {**VIEW, "columns": ["title", "nope"]})

    def test_all_views_merges_builtins(self) -> None:
        root = tempfile.mkdtemp(prefix="pl-views-")
        views.save(root, VIEW)
        values = views.all_views(root, "owner")
        ids = [view["id"] for view in values]
        self.assertIn("all", ids)
        self.assertIn("review-queue", ids)
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
