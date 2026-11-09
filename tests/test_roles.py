"""core/roles.py: the role catalog, project adjustments and task roles."""
from __future__ import annotations

import json
import sys
import unittest

from helpers import PACKAGE, make_project, run_tool, task

sys.path.insert(0, str(PACKAGE))

from core import factory, roles  # noqa: E402
from core.board import board_errors  # noqa: E402


def board10(*tasks):
    return {"schema_version": "1.0", "project": "t", "profile": "S", "base_branch": "main", "tasks": list(tasks)}


class Catalog(unittest.TestCase):
    def test_the_package_roles_are_consistent(self):
        self.assertEqual(roles.errors(None, factory.station_ids()), [])
        loaded = roles.load()
        self.assertIn("frontend-builder", loaded)
        self.assertTrue(all(role["mode"] in ("worker", "reviewer") for role in loaded.values()))

    def test_every_station_but_verify_and_operate_has_a_planner_or_builder(self):
        covered = {s for role in roles.load().values() for s in role["stations"]}
        self.assertTrue({"idea", "concept", "design", "architecture", "plan", "build", "verify", "release"} <= covered)

    def test_roles_page_is_current(self):
        text = (PACKAGE / "docs" / "roles.md").read_text(encoding="utf-8")
        self.assertEqual(text, roles.markdown(), "run: python3 scripts/roles-doc.py")


class Project(unittest.TestCase):
    def test_project_adjusts_and_adds_roles(self):
        root = make_project([])
        folder = root / "docs" / "roles"
        folder.mkdir(parents=True)
        (folder / "roles.json").write_text(json.dumps({"roles": [
            {"id": "frontend-builder", "name": "Lena", "writes": ["src/ui/"]},
            {"id": "data-engineer", "title": "Data engineer", "stations": ["build"], "mode": "worker",
             "model": "fast", "focus": "Imports.", "reads": [], "gates": ["tests"]},
        ]}))
        (folder / "data-engineer.md").write_text("Import data.\n")
        loaded = roles.load(root)
        self.assertEqual(loaded["frontend-builder"]["name"], "Lena")
        self.assertEqual(loaded["frontend-builder"]["writes"], ["src/ui/"])
        self.assertEqual(loaded["frontend-builder"]["mode"], "worker")
        self.assertEqual(roles.instructions("data-engineer", root), "Import data.")
        self.assertEqual(roles.errors(root), [])

    def test_a_role_cannot_grant_lead(self):
        root = make_project([])
        folder = root / "docs" / "roles"
        folder.mkdir(parents=True)
        (folder / "roles.json").write_text(json.dumps({"roles": [{"id": "reviewer", "mode": "lead"}]}))
        self.assertTrue(any("never grants lead" in e for e in roles.errors(root)))


class Tasks(unittest.TestCase):
    def test_role_is_a_1_0_field_with_an_id_shape(self):
        ok = task("M01", status="pending", role="frontend-builder")
        self.assertEqual([e for e in board_errors(board10(ok)) if "role" in e], [])
        bad = task("M01", status="pending", role="Frontend Builder")
        self.assertTrue(any("role must be" in e for e in board_errors(board10(bad))))

    def test_check_reports_an_unknown_role(self):
        root = make_project([task("M01", status="pending", role="astronaut")])
        data = json.loads((root / "board.json").read_text())
        data["schema_version"] = "1.0"
        (root / "board.json").write_text(json.dumps(data))
        result = run_tool("check.py", str(root))
        self.assertIn("unknown role 'astronaut'", result.stdout)


if __name__ == "__main__":
    unittest.main()
