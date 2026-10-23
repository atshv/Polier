"""tools/gate.py records and their verification in tools/check.py."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from helpers import make_project, run_tool, task

import check  # noqa: E402  (tools/ is on sys.path via helpers)


def gate(root: Path, name: str, code: int = 0, tid: str = "M01") -> str:
    result = run_tool("gate.py", "--task", tid, "--name", name, "--root", str(root), "--",
                      sys.executable, "-c", f"print('out'); raise SystemExit({code})")
    last = result.stdout.strip().splitlines()[-1]
    assert last.startswith("record: "), result.stdout
    return last.removeprefix("record: ")


def evidence_findings(root: Path) -> tuple[list[str], list[str]]:
    board = json.loads((root / "board.json").read_text())
    errors: list[str] = []
    warnings: list[str] = []
    check.check_evidence(root, board, errors, warnings)
    return errors, warnings


def set_done(root: Path, evidence: list[str], gates: list[str] | None = None) -> None:
    board = json.loads((root / "board.json").read_text())
    board["tasks"][0].update(status="done", evidence=evidence)
    if gates is not None:
        board["tasks"][0]["gates"] = gates
    (root / "board.json").write_text(json.dumps(board))


class GateRecords(unittest.TestCase):
    def test_unique_logs_and_record_fields(self):
        root = make_project([task()])
        first, second = gate(root, "tests"), gate(root, "tests")
        self.assertNotEqual(first, second)
        record = json.loads((root / first).read_text())
        for key in ("task", "gate", "command", "exit_code", "started", "finished",
                    "commit", "dirty", "log", "log_sha256"):
            self.assertIn(key, record)
        self.assertEqual(record["exit_code"], 0)
        self.assertEqual(len(record["commit"]), 40)
        self.assertTrue((root / "reviews/evidence" / record["log"]).is_file())

    def test_failed_gate_keeps_exit_code_and_prints_record(self):
        root = make_project([task()])
        result = run_tool("gate.py", "--task", "M01", "--name", "tests", "--root", str(root), "--",
                          sys.executable, "-c", "raise SystemExit(3)")
        self.assertEqual(result.returncode, 3)
        self.assertTrue(result.stdout.strip().splitlines()[-1].startswith("record: "))

    def test_name_with_dot(self):
        root = make_project([task()])
        rel = gate(root, "cli.smoke")
        self.assertTrue(rel.endswith(".json"))
        self.assertTrue((root / rel).is_file())


class EvidenceCheck(unittest.TestCase):
    def test_passing_records_cover_all_gates(self):
        root = make_project([task()])
        set_done(root, [gate(root, "lint"), gate(root, "tests")], gates=["lint", "tests"])
        errors, _ = evidence_findings(root)
        self.assertEqual(errors, [])

    def test_missing_record_file(self):
        root = make_project([task()])
        set_done(root, ["reviews/evidence/nope.json"])
        errors, _ = evidence_findings(root)
        self.assertTrue(any("missing" in e for e in errors), errors)

    def test_failed_gate_is_an_error_but_a_later_pass_covers_it(self):
        root = make_project([task()])
        bad = gate(root, "tests", code=1)
        set_done(root, [bad])
        errors, _ = evidence_findings(root)
        self.assertTrue(any("failed" in e for e in errors), errors)

        set_done(root, [gate(root, "tests")])
        errors, _ = evidence_findings(root)
        self.assertEqual(errors, [])

    def test_record_of_other_task(self):
        root = make_project([task()])
        set_done(root, [gate(root, "tests", tid="M09")])
        errors, _ = evidence_findings(root)
        self.assertTrue(any("belongs to task" in e for e in errors), errors)

    def test_edited_log_is_detected(self):
        root = make_project([task()])
        rel = gate(root, "tests")
        record = json.loads((root / rel).read_text())
        (root / "reviews/evidence" / record["log"]).write_text("all green, trust me\n")
        set_done(root, [rel])
        errors, _ = evidence_findings(root)
        self.assertTrue(any("checksum" in e for e in errors), errors)

    def test_uncovered_gate(self):
        root = make_project([task()])
        set_done(root, [gate(root, "tests")], gates=["tests", "lint"])
        errors, _ = evidence_findings(root)
        self.assertTrue(any("'lint'" in e for e in errors), errors)

    def test_free_text_only_warns(self):
        root = make_project([task()])
        set_done(root, ["pytest: 6 passed"])
        errors, warnings = evidence_findings(root)
        self.assertEqual(errors, [])
        self.assertTrue(any("free text" in w for w in warnings))

    def test_commit_not_in_history_warns(self):
        root = make_project([task()])
        rel = gate(root, "tests")
        record = json.loads((root / rel).read_text())
        record["commit"] = "0" * 40
        (root / rel).write_text(json.dumps(record))
        set_done(root, [rel])
        errors, warnings = evidence_findings(root)
        self.assertEqual(errors, [])
        self.assertTrue(any("history" in w for w in warnings), warnings)


if __name__ == "__main__":
    unittest.main()
