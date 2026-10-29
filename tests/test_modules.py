"""core/modules.py: packages as modules with tasks, docs, contracts and health."""
from __future__ import annotations

import unittest

from dash_helpers import sample_project

from core import modules


class ModulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_project()
        self.model = modules.build(self.root)

    def test_modules_follow_packages(self) -> None:
        paths = [module["path"] for module in self.model["modules"]]
        self.assertIn("packages/engine", paths)
        self.assertIn("apps/web", paths)
        self.assertEqual(self.model["totals"]["modules"], 4)

    def test_module_tasks_docs_and_health(self) -> None:
        engine = next(module for module in self.model["modules"]
                      if module["path"] == "packages/engine")
        self.assertGreater(engine["totals"]["tasks"], 0)
        self.assertTrue(engine["docs"])
        self.assertIn(engine["health"], ("ok", "watch", "attention", "done"))
        self.assertIn("health_reasons", engine)
        self.assertIn("progress", engine)

    def test_unassigned_tasks_are_visible(self) -> None:
        self.assertGreater(self.model["unassigned"]["count"], 0)
        self.assertEqual(self.model["unassigned"]["count"],
                         len(self.model["unassigned"]["tasks"]))


if __name__ == "__main__":
    unittest.main()
