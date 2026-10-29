"""core/task_templates.py: reusable task shapes."""
from __future__ import annotations

import unittest

from dash_helpers import sample_project

from core import task_templates
from core.errors import PolierError

TEMPLATE = {"id": "feature", "name": "Feature", "scope_write": ["docs/"],
            "acceptance": ["A1"], "gates": ["board-check"], "complexity": 3,
            "labels": ["feature"], "estimate_hours": 4}


class TaskTemplatesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_project()

    def test_save_list_defaults_delete(self) -> None:
        saved = task_templates.save(self.root, TEMPLATE)
        self.assertEqual(saved["id"], "feature")
        self.assertTrue((self.root / "templates" / "tasks" / "feature.json").is_file())
        self.assertEqual([template["id"] for template in task_templates.load_all(self.root)],
                         ["feature"])
        defaults = task_templates.defaults(self.root, "feature")
        self.assertEqual(defaults["gates"], ["board-check"])
        self.assertNotIn("id", defaults)
        task_templates.delete(self.root, "feature")
        self.assertEqual(task_templates.load_all(self.root), [])

    def test_from_task(self) -> None:
        template = task_templates.from_task(self.root, "F-01", "from-f01", name="From F-01")
        self.assertEqual(template["id"], "from-f01")
        self.assertEqual(template["scope_write"], ["ARCHITECTURE.md", "AGENTS.md", "README.md",
                                                   ".gitignore", ".env.example", "docs/",
                                                   "packages/", "services/", "apps/", "tools/layout_check.py"])
        self.assertEqual(template["gates"], ["layout"])

    def test_validation(self) -> None:
        with self.assertRaises(PolierError):
            task_templates.save(self.root, {**TEMPLATE, "id": "Bad"})
        with self.assertRaises(PolierError):
            task_templates.save(self.root, {**TEMPLATE, "complexity": 99})
        with self.assertRaises(PolierError):
            task_templates.save(self.root, {**TEMPLATE, "unknown": True})
        with self.assertRaises(KeyError):
            task_templates.get(self.root, "missing")


if __name__ == "__main__":
    unittest.main()
