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


# ---------------------------------------------------------------------------
# PL-03: exclusive gates, busy results and infrastructure classification.
# These classes are new; the tests above stay unchanged.
# ---------------------------------------------------------------------------

import datetime as _dt  # noqa: E402
import subprocess as _subprocess  # noqa: E402
import time as _time  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

from core.gate import write_record as _write_record  # noqa: E402
from core.locks import (  # noqa: E402
    acquire_lock as _acquire_lock,
    lock_path as _lock_path,
    release_lock as _release_lock,
)

GATE_TOOL = _Path(__file__).resolve().parents[2] / "tools" / "gate.py"


def _record_of(root, stdout: str) -> dict:
    last = stdout.strip().splitlines()[-1]
    assert last.startswith("record: "), stdout
    return json.loads((root / last[len("record: "):]).read_text())


def _holder(task_id: str = "other", **extra) -> dict:
    data = {
        "task": task_id,
        "slot": 1,
        "harness": "dsh",
        "pid": 1,
        "host": "elsewhere",
        "started": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }
    data.update(extra)
    return data


class Classification(unittest.TestCase):
    def test_pass_timeout_fail_infra_and_custom_patterns(self):
        root = project([task()])
        passed = run_gate(PY + ["print('ok')"], "M01", "tests", root)
        self.assertEqual((passed["exit_code"], passed["result"]), (0, "pass"))
        stored = json.loads(passed["record_path"].read_text())
        self.assertEqual(stored["result"], "pass")
        self.assertIsNone(stored["slot"])
        self.assertEqual(stored["exclusive"], [])
        self.assertEqual(stored["lock_wait_s"], 0.0)

        timed_out = run_gate(PY + ["import time; time.sleep(5)"], "M01", "slow", root, timeout=1)
        self.assertEqual((timed_out["exit_code"], timed_out["result"]), (124, "timeout"))

        failed = run_gate(PY + ["raise SystemExit(3)"], "M01", "tests", root)
        self.assertEqual((failed["exit_code"], failed["result"]), (3, "fail"))

        patterns = (
            "ECONNREFUSED",
            "ERR_CONNECTION_REFUSED",
            "EADDRINUSE",
            "is already used, make sure that nothing is running on the port",
            "Address already in use",
        )
        for index, text in enumerate(patterns):
            result = run_gate([sys.executable, "-c", f"print({text!r}); raise SystemExit(1)"],
                              "M01", f"infra{index}", root)
            self.assertEqual(result["result"], "infra", text)
            self.assertEqual(result["exit_code"], 1)

        custom = run_gate([sys.executable, "-c",
                           "print('MIGRATION_LOCK_TIMEOUT'); raise SystemExit(1)"],
                          "M01", "custom", root, infra_patterns=["MIGRATION_LOCK_TIMEOUT"])
        self.assertEqual(custom["result"], "infra")

    def test_slot_and_exclusive_fields_are_recorded_and_locks_released(self):
        root = project([task()])
        result = run_gate(PY + ["pass"], "M01", "tests", root, slot=2, exclusive=["e2e"])
        self.assertEqual((result["slot"], result["exclusive"]), (2, ["e2e"]))
        self.assertEqual(result["lock_wait_s"], 0.0)
        stored = json.loads(result["record_path"].read_text())
        self.assertEqual(stored["slot"], 2)
        self.assertEqual(stored["exclusive"], ["e2e"])
        self.assertEqual(stored["lock_wait_s"], 0.0)
        self.assertFalse(_lock_path(root, "e2e").exists())

    def test_command_not_found_keeps_127(self):
        root = project([task()])
        result = run_gate(["no-such-command-pl"], "M01", "x", root)
        self.assertEqual((result["exit_code"], result["result"]), (127, "fail"))


class ExclusiveGate(unittest.TestCase):
    def test_second_gate_waits_for_the_first(self):
        root = project([task()])
        sleep_command = [sys.executable, "-c", "import time; time.sleep(1.0)"]
        argv = [sys.executable, str(GATE_TOOL), "--task", "M01", "--name", "e2e",
                "--root", str(root), "--exclusive", "e2e", "--lock-wait", "30", "--"] + sleep_command
        first = _subprocess.Popen(argv, stdout=_subprocess.PIPE, stderr=_subprocess.PIPE, text=True)
        deadline = _time.time() + 15
        while _time.time() < deadline and not _lock_path(root, "e2e").exists():
            _time.sleep(0.01)
        self.assertTrue(_lock_path(root, "e2e").exists(), "the first gate did not take the lock")
        try:
            second = _subprocess.run(argv, capture_output=True, text=True, timeout=120)
            first_out, first_err = first.communicate(timeout=120)
        finally:
            if first.poll() is None:
                first.kill()
        self.assertEqual(first.returncode, 0, first_err)
        self.assertEqual(second.returncode, 0, second.stderr)

        first_record = _record_of(root, first_out)
        second_record = _record_of(root, second.stdout)
        self.assertEqual(first_record["exclusive"], ["e2e"])
        self.assertEqual(second_record["exclusive"], ["e2e"])
        self.assertEqual(second_record["result"], "pass")
        self.assertLess(first_record["lock_wait_s"], 0.2)
        self.assertGreater(second_record["lock_wait_s"], 0.3)
        self.assertFalse(_lock_path(root, "e2e").exists())

    def test_busy_resource_exits_75_without_running_the_command(self):
        root = project([task(exclusive=["e2e"])])
        set_board(root, schema_version="1.0", tasks=[task(exclusive=["e2e"])])
        _acquire_lock(root, "e2e", _holder())
        marker = root / "should-not-run.txt"
        command = [sys.executable, "-c", f"open({str(marker)!r}, 'w').write('x')"]
        try:
            result = _subprocess.run(
                [sys.executable, str(GATE_TOOL), "--task", "M01", "--name", "e2e",
                 "--root", str(root), "--lock-wait", "0.2", "--"] + command,
                capture_output=True, text=True, timeout=120)
        finally:
            _release_lock(root, "e2e")

        self.assertEqual(result.returncode, 75, result.stderr)
        self.assertFalse(marker.exists(), "the gate command ran although the resource was busy")
        lines = result.stdout.strip().splitlines()
        self.assertIn("BUSY", lines[0])
        self.assertIn("held by other", lines[0])
        self.assertIn("rerun alone", lines[0])
        self.assertTrue(lines[-1].startswith("record: "), lines)
        record = _record_of(root, result.stdout)
        self.assertEqual((record["exit_code"], record["result"]), (75, "busy"))
        self.assertEqual(record["exclusive"], [])
        self.assertGreaterEqual(record["lock_wait_s"], 0.1)


class RecordWriter(unittest.TestCase):
    def test_round_trip_and_never_overwrite(self):
        root = project([task()])
        started = _dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=_dt.timezone.utc)
        finished = _dt.datetime(2026, 1, 2, 3, 4, 9, tzinfo=_dt.timezone.utc)
        result = _write_record("M01", "smoke", root, command="echo ok", exit_code=0,
                               output="ok\n", result="pass", slot=2, exclusive=["e2e"],
                               lock_wait_s=1.5, started=started, finished=finished)
        stored = json.loads(result["record_path"].read_text())
        self.assertEqual(result["record_path"].name, "M01-smoke-20260102T030405Z.json")
        expected = {
            "task": "M01", "gate": "smoke", "command": "echo ok", "exit_code": 0,
            "result": "pass", "slot": 2, "exclusive": ["e2e"], "lock_wait_s": 1.5,
            "started": "2026-01-02T03:04:05+00:00",
            "finished": "2026-01-02T03:04:09+00:00",
            "log": result["log_path"].name,
            "log_sha256": result["log_sha256"],
        }
        for key, value in expected.items():
            self.assertEqual(stored[key], value, key)
        self.assertNotIn("output", stored)
        self.assertEqual(result["output"], "ok\n")
        self.assertEqual(result["root"], root)

        again = _write_record("M01", "smoke", root, command="echo ok", exit_code=0,
                              output="ok\n", result="pass", started=started)
        self.assertNotEqual(again["record_path"], result["record_path"])
        self.assertEqual(again["record_path"].name, "M01-smoke-20260102T030405Z-2.json")

        with self.assertRaises(ValueError):
            _write_record("M01/../x", "smoke", root, command="echo ok", exit_code=0, output="")


class GateEvidence(unittest.TestCase):
    def test_infrastructure_records_are_not_evidence(self):
        for result_name, code in (("infra", 1), ("busy", 75), ("timeout", 124)):
            root = project([task()])
            rel = _write_record("M01", "tests", root, command="x", exit_code=code,
                                output="boom\n", result=result_name
                                )["record_path"].relative_to(root).as_posix()
            board = {"tasks": [task(status="done", evidence=[rel], gates=["tests"])]}
            errors, warnings = verify_evidence(root, board)
            self.assertTrue(
                any("infrastructure failure, rerun alone" in error for error in errors),
                (result_name, errors))
            self.assertTrue(any("tests" in error and rel in error for error in errors),
                            (result_name, errors))
            self.assertFalse(any("no passing gate record" in error for error in errors),
                             (result_name, errors))
            self.assertEqual(warnings, [])

    def test_record_without_result_keeps_the_old_behaviour(self):
        root = project([task()])
        rel = _write_record("M01", "tests", root, command="x", exit_code=1,
                            output="boom\n")["record_path"].relative_to(root).as_posix()
        errors, _ = verify_evidence(root, {"tasks": [task(status="done", evidence=[rel])]})
        self.assertTrue(any("failed" in error for error in errors), errors)
        self.assertFalse(any("infrastructure" in error for error in errors), errors)

        passing_root = project([task()])
        passing = _write_record("M01", "tests", passing_root, command="x", exit_code=0,
                                output="ok\n")["record_path"].relative_to(passing_root).as_posix()
        self.assertEqual(
            verify_evidence(passing_root, {"tasks": [task(status="done", evidence=[passing])]}),
            ([], []))


class BoardPatterns(unittest.TestCase):
    def test_board_infra_patterns_reach_the_record(self):
        root = project([task()])
        set_board(root, schema_version="1.0",
                  resources={"infra_patterns": ["MY-LOCK-TIMEOUT"]})
        result = _subprocess.run(
            [sys.executable, str(GATE_TOOL), "--task", "M01", "--name", "tests",
             "--root", str(root), "--", sys.executable, "-c",
             "print('MY-LOCK-TIMEOUT'); raise SystemExit(1)"],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 1, result.stderr)
        record = _record_of(root, result.stdout)
        self.assertEqual(record["result"], "infra")

