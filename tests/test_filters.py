"""core/filters.py: structured filters, grouping and sorting."""
from __future__ import annotations

import unittest

from core import filters
from core.errors import PolierError

TASKS = [
    {"id": "A-01", "title": "Fix login", "status": "pending", "stage": "s1", "package": "apps/web",
     "owner": "owner", "labels": ["bug", "risk-high"], "ready": True, "running": False,
     "claim": None, "blocked_reason": None, "tokens": 10, "attempt": 0, "gates_missing": ["tests"],
     "complexity": 2, "estimate_hours": 3, "budget": {"over": True, "warn": True},
     "review": {"present": False, "verdict": None}},
    {"id": "A-02", "title": "Engine work", "status": "review", "stage": "s2", "package": "packages/engine",
     "owner": "lead", "labels": ["feature"], "ready": False, "running": True,
     "claim": {"harness": "dsh"}, "blocked_reason": None, "tokens": 50, "attempt": 1,
     "gates_missing": [], "complexity": 5, "budget": {"over": False, "warn": True},
     "review": {"present": True, "verdict": "pass"}},
]


class FiltersTest(unittest.TestCase):
    def test_validation(self) -> None:
        self.assertEqual(filters.validate([]), [])
        self.assertTrue(filters.validate([{"field": "nope", "op": "is", "value": "x"}]))
        self.assertTrue(filters.validate([{"field": "status", "op": "contains", "value": "x"}]))
        self.assertTrue(filters.validate([{"field": "token", "op": "is", "value": "x"}]))
        self.assertEqual(filters.validate([{"field": "label", "op": "any_of", "value": ["bug"]}]), [])
        self.assertEqual(filters.validate([{"field": "estimate_hours", "op": "empty"}]), [])

    def test_apply_and_operators(self) -> None:
        self.assertEqual([t["id"] for t in filters.apply(
            [{"field": "ready", "op": "is", "value": True}], TASKS)], ["A-01"])
        self.assertEqual([t["id"] for t in filters.apply(
            [{"field": "label", "op": "any_of", "value": ["bug"]}], TASKS)], ["A-01"])
        self.assertEqual([t["id"] for t in filters.apply(
            [{"field": "label", "op": "none_of", "value": ["bug"]}], TASKS)], ["A-02"])
        self.assertEqual([t["id"] for t in filters.apply(
            [{"field": "tokens", "op": "gte", "value": 50}], TASKS)], ["A-02"])
        self.assertEqual([t["id"] for t in filters.apply(
            [{"field": "budget", "op": "is", "value": "over"}], TASKS)], ["A-01"])
        self.assertEqual([t["id"] for t in filters.apply(
            [{"field": "status", "op": "any_of", "value": ["review", "verifying"]}], TASKS)],
            ["A-02"])
        self.assertEqual([t["id"] for t in filters.apply(
            [{"field": "review_verdict", "op": "empty"}], TASKS)], ["A-01"])
        with self.assertRaises(PolierError):
            filters.apply([{"field": "status", "op": "is", "value": "nonsense"}], TASKS)

    def test_group_and_sort(self) -> None:
        grouped = filters.group(TASKS, "status")
        self.assertEqual([group["key"] for group in grouped], ["pending", "review"])
        sorted_ids = [task["id"] for task in filters.sort(TASKS, "tokens", "desc")]
        self.assertEqual(sorted_ids, ["A-02", "A-01"])
        with self.assertRaises(PolierError):
            filters.group(TASKS, "nope")

    def test_builtin_views_are_valid(self) -> None:
        for view in filters.builtin_views("owner"):
            self.assertEqual(filters.validate(view["filters"]), [], view["id"])
            self.assertIn(view["group_by"], filters.GROUP_BY)


if __name__ == "__main__":
    unittest.main()
