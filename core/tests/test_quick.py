"""The entry rule of the quick track (ADR-0004)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from helpers import make_project, task  # noqa: E402

from core import quick  # noqa: E402
from core.errors import PolierError  # noqa: E402


POLICY = json.dumps({"enabled": True, "scope": {"protected_paths": ["policy.json"]}})


def line(root: Path, build: str = "done", items: dict | None = None) -> None:
    (root / "factory.json").write_text(json.dumps({
        "stations": {"build": {"status": build}}, "items": items or {}}))


def project(tasks=None, **kwargs) -> Path:
    root = make_project(tasks or [task("M01", "done", scope_write=["src/app.py"], gates=["lint", "tests"])])
    line(root, **kwargs)
    return root


class QualifiesTest(unittest.TestCase):
    def test_existing_file_after_build_is_accepted(self):
        ok, reasons = quick.qualifies(project(), ["src/app.py"], "Fix the crash")
        self.assertTrue(ok, reasons)

    def test_build_station_open_or_no_line_refuses(self):
        ok, reasons = quick.qualifies(project(build="in_progress"), ["src/app.py"], "Fix the crash")
        self.assertFalse(ok)
        self.assertIn("build station", reasons[0])
        root = make_project([task("M01", "done")])
        self.assertFalse(quick.qualifies(root, ["src/app.py"], "Fix the crash")[0])

    def test_quick_task_in_progress_refuses(self):
        root = project([task("M01", "in_progress", track="quick")])
        ok, reasons = quick.qualifies(root, ["src/app.py"], "Another fix")
        self.assertFalse(ok)
        self.assertTrue(any("already in progress" in r for r in reasons))

    def test_scope_edge_cases(self):
        root = project()
        for scope in ([], ["missing.py"], ["src"], ["../outside.py"], ["/etc/passwd"]):
            ok, reasons = quick.qualifies(root, scope, "Fix the crash")
            self.assertFalse(ok, scope)
            self.assertTrue(reasons)

    def test_protected_manifest_data_model_and_evidence(self):
        root = project(items={"BLD-11": {"status": "done", "evidence": ["README.md#intro"]}})
        for rel in ("policy.json", "package.json", "migrations/001.sql", "db/schema.sql"):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(POLICY if rel == "policy.json" else "{}\n")
        (root / "docs").mkdir()
        (root / "docs" / "data-model.md").write_text("Schema in `db/schema.sql`.\n")
        for rel, text in (("policy.json", "protected"), ("package.json", "manifest"),
                          ("migrations/001.sql", "data model"), ("db/schema.sql", "data model"),
                          ("docs/data-model.md", "data model"), ("README.md", "must item")):
            ok, reasons = quick.qualifies(root, [rel], "Fix the crash")
            self.assertFalse(ok, rel)
            self.assertTrue(any(text in r for r in reasons), (rel, reasons))

    def test_title_length(self):
        self.assertFalse(quick.qualifies(project(), ["src/app.py"], "x")[0])


class CreateTest(unittest.TestCase):
    def test_default_gates_role_and_next_free_id_after_deleted_task(self):
        root = project([task("M01", "done", scope_write=["src/app.py"], gates=["lint", "tests"], role="backend-builder")])
        (root / "tasks").mkdir()
        (root / "tasks" / "M02.md").write_text("# M02 — gone\n")  # a deleted task left its brief
        made = quick.create(root, "Fix the crash", ["src/app.py"])
        self.assertEqual(made["task"], "M03")
        entry = json.loads((root / "board.json").read_text())["tasks"][-1]
        self.assertEqual((entry["track"], entry["status"], entry["gates"], entry["role"]),
                         ("quick", "pending", ["lint", "tests"], "backend-builder"))
        self.assertTrue((root / "tasks" / "M03.md").is_file())

    def test_gates_default_to_tests_and_can_be_given(self):
        root = project([task("M01", "done", scope_write=["other.py"])])
        self.assertEqual(quick.create(root, "Fix README", ["README.md"])["gates"], ["tests"])
        self.assertEqual(quick.create(root, "Fix README again", ["README.md"], ["lint"])["gates"], ["lint"])

    def test_refusal_raises_and_writes_nothing(self):
        root = project()
        before = (root / "board.json").read_text()
        with self.assertRaises(PolierError):
            quick.create(root, "Fix", ["missing.py"])
        self.assertEqual((root / "board.json").read_text(), before)


if __name__ == "__main__":
    unittest.main()
