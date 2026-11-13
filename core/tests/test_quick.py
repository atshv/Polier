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


ACCEPT = ["WHEN the input is empty, THEN the command exits 2 with a message"]


def project(tasks=None, **kwargs) -> Path:
    root = make_project(tasks or [task("M01", "done", scope_write=["src/app.py"], gates=["lint", "tests"],
                                       satisfies=["D1"])])
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "quality.md").write_text("- **D1** It works.\n- **D2** Docs exist.\n")
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

    def test_any_open_quick_task_refuses_a_second_one(self):
        for status in ("pending", "claimed", "in_progress", "verifying", "review", "rework", "blocked"):
            root = project([task("M01", status, track="quick")])
            ok, reasons = quick.qualifies(root, ["src/app.py"], "Another fix")
            self.assertFalse(ok, status)
            self.assertTrue(any("still open" in r for r in reasons), status)
        for status in ("done", "failed"):
            root = project([task("M01", status, track="quick")])
            self.assertTrue(quick.qualifies(root, ["src/app.py"], "Another fix")[0], status)

    def test_second_quick_task_is_refused_while_the_first_is_pending(self):
        root = project()
        quick.create(root, "First fix", ["src/app.py"], ACCEPT)
        with self.assertRaises(quick.Refused):
            quick.create(root, "Second fix", ["src/app.py"], ACCEPT)

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
        (root / "docs").mkdir(exist_ok=True)
        (root / "docs" / "data-model.md").write_text("Schema in `db/schema.sql`.\n")
        for rel, text in (("policy.json", "protected"), ("package.json", "manifest"),
                          ("migrations/001.sql", "data model"), ("db/schema.sql", "data model"),
                          ("docs/data-model.md", "data model"), ("README.md", "must item")):
            ok, reasons = quick.qualifies(root, [rel], "Fix the crash")
            self.assertFalse(ok, rel)
            self.assertTrue(any(text in r for r in reasons), (rel, reasons))

    def test_record_and_plan_paths_are_refused_without_a_policy(self):
        root = project()
        paths = ["factory.json", "board.json", "policy.json", "STATUS.md", "docs/factory.md",
                 "runs/M01.json", "reviews/M01.md", "reviews/approvals/A1.json",
                 "reviews/evidence/M01-tests.log", "changes/C01/proposal.md", "tasks/M01.md"]
        for rel in paths:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text("{}\n" if rel == "policy.json" else "x\n")
            ok, reasons = quick.qualifies(root, [rel], "Fix the crash")
            self.assertFalse(ok, rel)
            self.assertTrue(any("record or plan file" in r and "factory.json" in r for r in reasons), rel)

    def test_title_length(self):
        self.assertFalse(quick.qualifies(project(), ["src/app.py"], "x")[0])


class CreateTest(unittest.TestCase):
    def test_default_gates_role_satisfies_and_next_free_id_after_deleted_task(self):
        root = project([task("M01", "done", scope_write=["src/app.py"], gates=["lint", "tests"],
                             role="backend-builder", satisfies=["D2"])])
        (root / "tasks").mkdir(exist_ok=True)
        (root / "tasks" / "M02.md").write_text("# M02 — gone\n")  # a deleted task left its brief
        made = quick.create(root, "Fix the crash", ["src/app.py"], ACCEPT)
        self.assertEqual(made["task"], "M03")
        entry = json.loads((root / "board.json").read_text())["tasks"][-1]
        self.assertEqual((entry["track"], entry["status"], entry["gates"], entry["role"], entry["satisfies"]),
                         ("quick", "pending", ["lint", "tests"], "backend-builder", ["D2"]))
        self.assertEqual(entry["acceptance"], ["A1"])
        brief = (root / "tasks" / "M03.md").read_text()
        self.assertIn("A1 WHEN the input is empty, THEN", brief)
        self.assertNotIn("UI specification", brief)
        self.assertNotIn("<", brief.replace("<br>", ""))

    def test_gates_default_to_tests_and_can_be_given(self):
        root = project([task("M01", "done", scope_write=["other.py"], satisfies=["D1"])])
        first = quick.create(root, "Fix README", ["README.md"], ACCEPT, satisfies=["D1"])
        self.assertEqual(first["gates"], ["tests"])
        json_board = json.loads((root / "board.json").read_text())
        json_board["tasks"][-1]["status"] = "done"
        (root / "board.json").write_text(json.dumps(json_board))
        self.assertEqual(quick.create(root, "Fix README again", ["README.md"], ACCEPT, ["lint"])["gates"], ["lint"])

    def test_accept_is_required_and_must_read_when_then(self):
        root = project()
        for bad in ([], [" "], ["fix it"], ["WHEN x happens"]):
            with self.assertRaises(PolierError) as caught:
                quick.create(root, "Fix the crash", ["src/app.py"], bad)
            self.assertNotIsInstance(caught.exception, quick.Refused)

    def test_satisfies_comes_from_last_toucher_or_the_caller_only(self):
        root = project([task("M01", "done", scope_write=["other.py"], satisfies=["D1"])])
        with self.assertRaises(PolierError) as caught:  # nobody touched src/app.py: no fallback
            quick.create(root, "Fix the crash", ["src/app.py"], ACCEPT)
        self.assertIn("--satisfies", str(caught.exception))
        with self.assertRaises(PolierError):
            quick.create(root, "Fix the crash", ["src/app.py"], ACCEPT, satisfies=["D9"])
        quick.create(root, "Fix the crash", ["src/app.py"], ACCEPT, satisfies=["D2"])
        self.assertEqual(json.loads((root / "board.json").read_text())["tasks"][-1]["satisfies"], ["D2"])

    def test_refusal_raises_and_writes_nothing(self):
        root = project()
        before = (root / "board.json").read_text()
        with self.assertRaises(quick.Refused):
            quick.create(root, "Fix", ["missing.py"], ACCEPT)
        self.assertEqual((root / "board.json").read_text(), before)
        self.assertFalse((root / "tasks").exists())


if __name__ == "__main__":
    unittest.main()
