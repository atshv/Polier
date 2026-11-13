"""tools/retro.py and core/retro.py on copies of the reference fixtures."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import PACKAGE, run_tool

sys.path.insert(0, str(PACKAGE))

from core import retro  # noqa: E402

FIXTURES = PACKAGE / "tests" / "fixtures"


def copy(name: str) -> Path:
    target = Path(tempfile.mkdtemp(prefix="pl-retro-")) / name
    shutil.copytree(FIXTURES / name, target)
    return target


def snapshot(root: Path) -> dict:
    return {str(p.relative_to(root)): p.stat().st_mtime_ns for p in sorted(root.rglob("*"))}


def gate_record(root: Path, name: str, task: str, gate: str, exit_code: int, result: str) -> None:
    folder = root / "reviews" / "evidence"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.json").write_text(json.dumps({
        "task": task, "gate": gate, "exit_code": exit_code, "result": result,
        "started": "2026-10-25T01:00:00+00:00", "finished": "2026-10-25T01:00:05+00:00",
        "log": f"{name}.log"}))


def write_run(root: Path, task: str, gates: list) -> None:
    """A run record with one attempt per distinct number in `gates` = (gate, result, attempt)."""
    numbers = sorted({n for _, _, n in gates})
    attempts = [{"n": n, "started": f"2026-10-25T0{n}:00:00+00:00", "ended": None, "result": None,
                 "note": None} for n in numbers]
    events = [{"at": f"2026-10-25T0{n}:30:00+00:00", "kind": "gate",
               "data": {"gate": g, "result": r, "record": f"reviews/evidence/{task}-{g}-{n}.json"}}
              for g, r, n in gates]
    (root / "runs").mkdir(exist_ok=True)
    (root / "runs" / f"{task}.json").write_text(json.dumps(
        {"task": task, "state": "failed", "attempt": len(attempts), "attempts": attempts,
         "events": events, "usage": {}, "updated": None}))


class RetroTest(unittest.TestCase):
    def test_a1_monorepo_prints_class_count_example_and_target(self):
        root = copy("monorepo-mini")
        result = run_tool("retro.py", str(root))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("stalled approval (1)", result.stdout)
        self.assertIn("AP-001.json", result.stdout)
        self.assertIn("prompt/orchestration.md", result.stdout)

    def test_every_class_with_a_signal(self):
        root = copy("minimal-cli")
        write_run(root, "M01", [("tests", "fail", 1), ("tests", "fail", 2)])
        gate_record(root, "M01-lint-3", "M01", "lint", 1, "busy")
        gate_record(root, "M01-lint-4", "M01", "lint", 1, "timeout")
        (root / "reviews" / "M02.md").write_text(
            "verdict: rework\n- criterion: \"A2\"\n\nverdict: pass\n")
        board = json.loads((root / "board.json").read_text())
        board["open_questions"].append({"id": "Q9", "question": "Needs a file outside the scope?"})
        (root / "board.json").write_text(json.dumps(board))
        (root / "factory.json").write_text(json.dumps(
            {"items": {"BLD-1": {"status": "deferred", "reason": "later"},
                       "BLD-2": {"status": "na", "reason": "no"}, "BLD-3": {"status": "done"}}}))
        found = {c["class"]: c for c in retro.report([root])["classes"]}
        self.assertEqual(found["repeated gate failure"]["count"], 1)
        self.assertIn("2 attempts", found["repeated gate failure"]["examples"][0]["detail"])
        self.assertEqual(found["busy or infra gate"]["count"], 2)
        self.assertEqual(found["long review"]["count"], 1)
        self.assertIn("A2", found["long review"]["examples"][0]["detail"])
        self.assertEqual(found["scope pressure"]["count"], 1)
        self.assertEqual(found["deferred or n/a item"]["count"], 2)
        for entry in found.values():
            self.assertTrue(entry["points_at"] and entry["examples"])

    def test_failures_in_one_attempt_are_not_repeated(self):
        root = copy("minimal-cli")
        write_run(root, "M01", [("tests", "fail", 1), ("tests", "fail", 1), ("lint", "fail", 1),
                                ("lint", "pass", 2), ("tests", "busy", 2)])
        names = [c["class"] for c in retro.report([root])["classes"]]
        self.assertNotIn("repeated gate failure", names)

    def test_review_criteria_with_quotes_are_grouped_by_heading(self):
        root = copy("minimal-cli")
        review = ("verdict: rework\n"
                  "- criterion: \"A2 / brief scope table ('Scored outcome (both arms)')\"\n"
                  "- criterion: \"Scope ('.gitignore: evals/results/')\"\n"
                  "verdict: pass\n")
        (root / "reviews" / "M05.md").write_text(review)
        (root / "reviews" / "M06.md").write_text(review.replace("Scope (", "Scope2 ("))
        found = {c["class"]: c for c in retro.report([root])["classes"]}["long review"]
        self.assertEqual(found["by_heading"], {"A2": 2, "Scope": 1, "Scope2": 1})
        for example in found["examples"]:
            self.assertNotIn("(,", example["detail"])
            self.assertIn("A2, Scope", example["detail"].replace("Scope2", "Scope") )

    def test_example_path_is_the_record_file_even_without_a_log(self):
        root = copy("minimal-cli")
        gate_record(root, "odd-name", "M01", "tests", 1, "busy")
        (root / "reviews" / "evidence" / "odd-name.json").write_text(json.dumps(
            {"task": "M01", "gate": "tests", "exit_code": 1, "result": "busy"}))
        found = {c["class"]: c for c in retro.report([root])["classes"]}["busy or infra gate"]
        self.assertTrue(found["examples"][0]["record"].endswith("reviews/evidence/odd-name.json"))

    def test_stalled_threshold_is_in_the_report(self):
        result = run_tool("retro.py", str(copy("monorepo-mini")))
        self.assertIn(f"threshold {retro.STALL_DAYS}", result.stdout)

    def test_busy_and_infra_records_are_not_failures(self):
        root = copy("minimal-cli")
        gate_record(root, "a", "M01", "tests", 1, "busy")
        gate_record(root, "b", "M01", "tests", 1, "infra")
        names = [c["class"] for c in retro.report([root])["classes"]]
        self.assertNotIn("repeated gate failure", names)
        self.assertIn("busy or infra gate", names)

    def test_a2_folder_without_records_is_skipped(self):
        empty = Path(tempfile.mkdtemp(prefix="pl-retro-empty-"))
        result = run_tool("retro.py", str(empty))
        self.assertEqual(result.returncode, 1)
        self.assertIn("Skipped", result.stdout)
        mixed = run_tool("retro.py", str(empty), str(copy("monorepo-mini")), "--json")
        self.assertEqual(mixed.returncode, 0)
        self.assertEqual(len(json.loads(mixed.stdout)["skipped"]), 1)

    def test_a3_nothing_changes_in_the_folders(self):
        root = copy("monorepo-mini")
        before = snapshot(root)
        run_tool("retro.py", str(root))
        run_tool("retro.py", str(root), "--json")
        self.assertEqual(snapshot(root), before)

    def test_a4_write_only_to_path_and_refuse_inside(self):
        root = copy("monorepo-mini")
        before = snapshot(root)
        out = Path(tempfile.mkdtemp(prefix="pl-retro-out-")) / "retro.md"
        result = run_tool("retro.py", str(root), "--write", str(out))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("stalled approval", out.read_text())
        self.assertEqual(result.stdout, "")
        self.assertEqual(snapshot(root), before)
        refused = run_tool("retro.py", str(root), "--write", str(root / "reviews" / "retro.md"))
        self.assertEqual(refused.returncode, 2)
        self.assertFalse((root / "reviews" / "retro.md").exists())

    def test_a5_json_is_one_object_on_stdout(self):
        result = run_tool("retro.py", str(copy("monorepo-mini")), "--json")
        data = json.loads(result.stdout)
        self.assertEqual(sorted(data)[:2], ["classes", "skipped"])
        self.assertEqual(data["classes"][0]["class"], "stalled approval")

    def test_usage_errors_exit_2(self):
        root = copy("monorepo-mini")
        self.assertEqual(run_tool("retro.py", str(root) + "-missing").returncode, 2)
        self.assertEqual(run_tool("retro.py", str(root), "--since", "yesterday").returncode, 2)
        self.assertEqual(run_tool("retro.py").returncode, 2)

    def test_since_drops_older_records(self):
        root = copy("monorepo-mini")
        self.assertEqual(run_tool("retro.py", str(root), "--since", "2026-10-01", "--json").returncode, 0)
        later = json.loads(run_tool("retro.py", str(root), "--since", "2026-10-26", "--json").stdout)
        self.assertEqual(later["classes"], [])

    def test_folder_given_twice_counts_once_and_broken_record_is_named(self):
        root = copy("monorepo-mini")
        (root / "reviews" / "approvals" / "AP-002.json").write_text("{broken")
        result = retro.report([root, root])
        self.assertEqual(result["classes"][0]["count"], 1)
        self.assertEqual(len(result["skipped"]), 1)
        self.assertIn("AP-002.json", result["skipped"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
