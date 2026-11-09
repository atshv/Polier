"""The software factory line: catalog, factory.json, evidence and stations."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from helpers import PACKAGE, make_project, run_tool, task

sys.path.insert(0, str(PACKAGE))

from core import factory  # noqa: E402
from core.errors import PolierError  # noqa: E402


def run(root, *args):
    return run_tool("factory.py", "--root", str(root), *args)


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def board(root: Path) -> dict:
    return json.loads((root / "board.json").read_text())


def set_board_status(root: Path, task_id: str, status: str) -> None:
    data = board(root)
    for entry in data["tasks"]:
        if entry["id"] == task_id:
            entry["status"] = status
    (root / "board.json").write_text(json.dumps(data, indent=2))


def close_idea(root: Path) -> None:
    write(root, "project-input.md", "# Input\n\nPROJECT: notes\n")
    for item_id in ("IDEA-01", "IDEA-02", "IDEA-03", "IDEA-04"):
        factory.set_item(root, item_id, "done", evidence=["project-input.md"])
    factory.set_item(root, "IDEA-05", "done", evidence=["factory.json"])
    factory.set_item(root, "IDEA-06", "deferred", reason="no budget yet")
    factory.advance(root, "owner")


class Catalog(unittest.TestCase):
    def test_the_catalog_is_consistent(self):
        catalog = factory.load_catalog()
        self.assertEqual(factory.catalog_errors(catalog), [])
        self.assertEqual(factory.station_ids(catalog),
                         ["idea", "concept", "design", "architecture", "plan",
                          "build", "verify", "release", "operate"])

    def test_catalog_markdown_is_in_sync(self):
        text = (PACKAGE / "factory" / "CATALOG.md").read_text(encoding="utf-8")
        self.assertEqual(text, factory.catalog_markdown(),
                         "run: python3 tools/factory.py catalog --write")

    def test_every_platform_has_release_items(self):
        catalog = factory.load_catalog()
        for platform in catalog["platforms"]:
            traits = factory.resolve_traits([platform], [], catalog)
            stations = {item["station"] for item in factory.applicable_items([platform], traits, catalog)}
            self.assertTrue({"idea", "architecture", "plan", "build", "verify", "release", "operate"} <= stations,
                            platform)

    def test_platforms_imply_traits(self):
        self.assertIn("ui", factory.resolve_traits(["ios"], []))
        self.assertIn("deploys", factory.resolve_traits(["web"], []))
        self.assertIn("personal_data", factory.resolve_traits(["cli"], ["accounts"]))
        self.assertEqual(factory.resolve_traits(["cli"], []), [])

    def test_applicability_needs_platform_and_trait(self):
        item = factory.catalog_item("REL-IOS-08")  # ios + payments
        self.assertTrue(factory.applies(item, ["ios"], ["payments"]))
        self.assertFalse(factory.applies(item, ["ios"], []))
        self.assertFalse(factory.applies(item, ["android"], ["payments"]))

    def test_mobile_items_only_for_mobile(self):
        ids = {i["id"] for i in factory.applicable_items(["web"], factory.resolve_traits(["web"], []))}
        self.assertNotIn("REL-IOS-01", ids)
        self.assertIn("REL-WEB-01", ids)
        ids = {i["id"] for i in factory.applicable_items(["ios"], factory.resolve_traits(["ios"], []))}
        self.assertIn("REL-IOS-01", ids)
        self.assertIn("BLD-65", ids)
        self.assertNotIn("REL-AND-01", ids)


class Init(unittest.TestCase):
    def test_init_writes_the_line(self):
        root = make_project([task("M01", status="pending")])
        result = run(root, "init", "--platforms", "web,ios", "--traits", "accounts", "--by", "owner")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads((root / "factory.json").read_text())
        self.assertEqual(data["platforms"], ["ios", "web"])
        self.assertEqual(data["stations"]["idea"]["status"], "active")
        self.assertIn("BLD-30", data["items"])
        self.assertIn("REL-IOS-03", data["items"])
        self.assertNotIn("REL-AND-03", data["items"])
        self.assertEqual(data["history"][0]["event"], "init")

    def test_init_refuses_unknown_platform_and_existing_file(self):
        root = make_project([])
        self.assertEqual(run(root, "init", "--platforms", "toaster").returncode, 2)
        self.assertEqual(run(root, "init", "--platforms", "cli").returncode, 0)
        result = run(root, "init", "--platforms", "web")
        self.assertEqual(result.returncode, 2)
        self.assertIn("exists", result.stderr)

    def test_rescope_adds_and_drops_items(self):
        root = make_project([])
        factory.init(root, ["web"], [])
        result = factory.rescope(root, platforms=["web", "android"], traits=None)
        self.assertIn("REL-AND-01", result["added"])
        result = factory.rescope(root, platforms=["web"], traits=None)
        self.assertIn("REL-AND-01", result["dropped"])
        data = factory.load(root)
        self.assertEqual(data["items"]["REL-AND-01"]["status"], "na")


class Items(unittest.TestCase):
    def setUp(self):
        self.root = make_project([task("M01", status="pending"), task("M02", status="pending")])
        factory.init(self.root, ["web"], ["accounts"])

    def test_done_needs_existing_evidence(self):
        with self.assertRaises(PolierError):
            factory.set_item(self.root, "IDEA-01", "done")
        with self.assertRaises(PolierError):
            factory.set_item(self.root, "IDEA-01", "done", evidence=["project-input.md"])
        write(self.root, "project-input.md", "x\n")
        entry = factory.set_item(self.root, "IDEA-01", "done", evidence=["project-input.md"], by="owner")
        self.assertEqual(entry["status"], "done")

    def test_anchor_must_be_a_heading(self):
        write(self.root, "docs/concept.md", "# Concept\n\n## Personas\n\nAna, 34.\n")
        with self.assertRaises(PolierError):
            factory.set_item(self.root, "CON-02", "done", evidence=["docs/concept.md#features"])
        factory.set_item(self.root, "CON-01", "done", evidence=["docs/concept.md#personas"])

    def test_evidence_outside_the_project_is_refused(self):
        with self.assertRaises(PolierError):
            factory.set_item(self.root, "IDEA-01", "done", evidence=["../etc/passwd"])

    def test_must_items_cannot_be_deferred(self):
        with self.assertRaises(PolierError):
            factory.set_item(self.root, "IDEA-01", "deferred", reason="later")
        factory.set_item(self.root, "IDEA-06", "deferred", reason="no budget yet")

    def test_na_needs_a_reason(self):
        with self.assertRaises(PolierError):
            factory.set_item(self.root, "IDEA-06", "na", reason="")
        result = run(self.root, "na", "IDEA-06", "--reason", "hobby project")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_task_items_need_done_tasks(self):
        with self.assertRaises(PolierError):
            factory.set_item(self.root, "BLD-30", "done")
        factory.link(self.root, "BLD-30", ["M01"])
        with self.assertRaises(PolierError):
            factory.set_item(self.root, "BLD-30", "done")
        set_board_status(self.root, "M01", "done")
        factory.set_item(self.root, "BLD-30", "done")
        set_board_status(self.root, "M01", "rework")
        report = factory.evaluate(self.root)
        self.assertTrue(any("M01 is rework" in e for e in report["errors"]))

    def test_link_refuses_unknown_tasks_and_out_of_scope_items(self):
        with self.assertRaises(PolierError):
            factory.link(self.root, "BLD-30", ["M99"])
        with self.assertRaises(PolierError):
            factory.link(self.root, "REL-IOS-01", ["M01"])


class Stations(unittest.TestCase):
    def test_advance_needs_resolved_items_and_an_owner(self):
        root = make_project([])
        factory.init(root, ["cli"], [])
        with self.assertRaises(PolierError):
            factory.advance(root, "")
        with self.assertRaises(PolierError):
            factory.advance(root, "owner")
        close_idea(root)
        data = factory.load(root)
        self.assertEqual(data["stations"]["idea"]["status"], "done")
        self.assertEqual(data["stations"]["idea"]["approved_by"], "owner")
        self.assertEqual(data["stations"]["concept"]["status"], "active")

    def test_empty_stations_are_skipped(self):
        root = make_project([])
        factory.init(root, ["cli"], [])
        close_idea(root)
        write(root, "docs/concept.md", "# C\n\n## Features\n\n## User stories\n")
        write(root, "docs/quality.md", "# Q\n")
        factory.set_item(root, "CON-02", "done", evidence=["docs/concept.md#features"])
        factory.set_item(root, "CON-03", "done", evidence=["docs/concept.md#user-stories"])
        factory.set_item(root, "CON-04", "done", evidence=["docs/quality.md"])
        for item_id in ("CON-01", "CON-05", "CON-06", "CON-10"):
            factory.set_item(root, item_id, "deferred", reason="small tool")
        result = factory.advance(root, "owner")
        # A CLI has a command interface, so design is not empty.
        self.assertEqual(result["opened"], "design")
        factory.set_item(root, "DES-15", "na", reason="single command")
        result = factory.advance(root, "owner")
        self.assertEqual(result["opened"], "architecture")

    def test_skip_without_items(self):
        root = make_project([])
        factory.init(root, ["service"], [])
        close_idea(root)
        write(root, "docs/q.md", "x")
        for item_id, entry in factory.load(root)["items"].items():
            if item_id.startswith("CON-"):
                factory.set_item(root, item_id, "na", reason="test")
        result = factory.advance(root, "owner")
        self.assertIn("design", result["closed"])
        self.assertEqual(result["opened"], "architecture")
        self.assertEqual(factory.load(root)["stations"]["design"]["approved_by"], "auto")

    def test_plan_station_needs_every_build_item_mapped(self):
        root = make_project([task("M01", status="pending")])
        factory.init(root, ["cli"], [])
        data = factory.load(root)
        for station in ("idea", "concept", "design", "architecture"):
            data["stations"][station] = {"status": "done", "approved_by": "owner"}
        data["stations"]["plan"] = {"status": "active"}
        for item_id in list(data["items"]):
            if item_id.startswith(("IDEA", "CON", "DES", "ARC", "PLN")):
                data["items"][item_id] = {"status": "na", "reason": "test"}
        factory.save(root, data)
        blockers = factory.station_blockers(root, factory.load(root), "plan")
        self.assertTrue(any("without a task" in b for b in blockers))
        for item_id in factory.unmapped(factory.load(root)):
            factory.link(root, item_id, ["M01"])
        self.assertEqual(factory.station_blockers(root, factory.load(root), "plan"), [])

    def test_started_task_before_plan_warns(self):
        root = make_project([task("M01", status="in_progress")])
        factory.init(root, ["cli"], [])
        report = factory.evaluate(root)
        self.assertTrue(any("before the plan station" in w for w in report["warnings"]))


class Tooling(unittest.TestCase):
    def test_render_status_next_and_check(self):
        root = make_project([task("M01", status="pending")])
        run(root, "init", "--platforms", "web")
        self.assertEqual(run(root, "render").returncode, 0)
        text = (root / "docs" / "factory.md").read_text()
        self.assertIn("## Idea — active", text)
        self.assertIn("REL-WEB-01", text)
        result = run(root, "next", "--json")
        value = json.loads(result.stdout)
        self.assertEqual(value["station"], "idea")
        self.assertTrue(value["items"])
        self.assertEqual(run(root, "check").returncode, 0)

    def test_check_py_reports_factory_errors(self):
        root = make_project([task("M01", status="pending")])
        factory.init(root, ["cli"], [])
        data = factory.load(root)
        data["items"]["IDEA-01"] = {"status": "done", "evidence": ["missing.md"]}
        factory.save(root, data)
        errors, _ = factory.check(root)
        self.assertTrue(any("missing.md does not exist" in e for e in errors))

    def test_status_line(self):
        root = make_project([])
        factory.init(root, ["cli"], [])
        self.assertTrue(factory.status_line(root).startswith("Factory: **idea 0/"))
        self.assertEqual(factory.status_line(make_project([])), "")

    def test_show_and_catalog_scope(self):
        root = make_project([])
        factory.init(root, ["android"], [])
        result = run(root, "show", "REL-AND-06")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("status: open", result.stdout)
        result = run(root, "catalog", "--platforms", "android")
        self.assertIn("REL-AND-06", result.stdout)
        self.assertNotIn("REL-IOS-01", result.stdout)



class Example(unittest.TestCase):
    def test_the_factory_example_holds(self):
        root = PACKAGE / "examples" / "factory-app"
        report = factory.evaluate(root)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["current"], "design")
        self.assertEqual((root / "docs" / "factory.md").read_text(encoding="utf-8"),
                         factory.render_markdown(root), "run: tools/factory.py --root examples/factory-app render")


if __name__ == "__main__":
    unittest.main()
