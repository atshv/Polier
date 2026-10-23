"""core.gate and core.evidence without the CLI."""
from __future__ import annotations

import json
import sys
import unittest

from core.evidence import verify_evidence
from core.gate import run_gate, summary

from .fixtures import project, set_board, task

PY = [sys.executable, "-c"]


class RunGate(unittest.TestCase):
    def test_pass_writes_log_and_record(self):
        root = project([task()])
        result = run_gate(PY + ["print('ok')"], "M01", "tests", root)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(len(result["commit"]), 40)
        self.assertFalse(result["dirty"])
        stored = json.loads(result["record_path"].read_text())
        self.assertEqual(stored["log_sha256"], result["log_sha256"])
        self.assertNotIn("output", stored)
        lines = summary(result)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("GATE tests: PASS (exit 0) — 1 lines in "))
        self.assertTrue(lines[-1].startswith("record: reviews/evidence/M01-tests-"))

    def test_records_are_never_overwritten(self):
        root = project([task()])
        first = run_gate(PY + ["pass"], "M01", "tests", root)["record_path"]
        second = run_gate(PY + ["pass"], "M01", "tests", root)["record_path"]
        self.assertNotEqual(first, second)

    def test_failure_shell_timeout_and_missing_command(self):
        root = project([task()])
        failed = run_gate("echo boom error; exit 3", "M01", "tests", root, shell=True)
        self.assertEqual(failed["exit_code"], 3)
        lines = summary(failed)
        self.assertEqual(lines[0], "GATE tests: FAIL (exit 3) — echo boom error; exit 3")
        self.assertIn("boom error", lines)
        self.assertEqual(run_gate(PY + ["import time; time.sleep(5)"], "M01", "slow", root, timeout=1)["exit_code"], 124)
        self.assertEqual(run_gate(["no-such-command-pl"], "M01", "x", root)["exit_code"], 127)

    def test_invalid_input(self):
        root = project([task()])
        with self.assertRaises(ValueError):
            run_gate(["true"], "M01/../x", "tests", root)
        with self.assertRaises(ValueError):
            run_gate([], "M01", "tests", root)
        with self.assertRaises(ValueError):
            run_gate(["true"], "M01", "tests", root, shell=True)


class VerifyEvidence(unittest.TestCase):
    def test_done_task_needs_a_passing_record_per_gate(self):
        root = project([task()])
        good = run_gate(PY + ["pass"], "M01", "tests", root)["record_path"].relative_to(root).as_posix()
        set_board(root, tasks=[task(status="done", evidence=[good])])
        board = json.loads((root / "board.json").read_text())
        self.assertEqual(verify_evidence(root, board), ([], []))

        board["tasks"][0]["gates"] = ["tests", "lint"]
        errors, _ = verify_evidence(root, board)
        self.assertEqual(errors, ["M01: no passing gate record for 'lint' (run it with tools/gate.py --name lint)"])

    def test_tampered_log(self):
        root = project([task()])
        result = run_gate(PY + ["pass"], "M01", "tests", root)
        result["log_path"].write_text("all green\n")
        rel = result["record_path"].relative_to(root).as_posix()
        errors, _ = verify_evidence(root, {"tasks": [task(status="done", evidence=[rel])]})
        self.assertTrue(any("checksum mismatch" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
