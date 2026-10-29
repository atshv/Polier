"""core/worklog.py: effort derived from runs, evidence and sessions."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core import runtime, worklog

BOARD = {
    "project": "demo", "profile": "S", "base_branch": "main", "schema_version": "1.1",
    "tasks": [{"id": "T-01", "title": "A task", "goal": "Do it.", "status": "done",
               "depends_on": [], "complexity": 2, "stage": 1, "scope_write": ["src/"],
               "acceptance": ["A1"], "gates": ["tests"], "estimate_hours": 1.0}],
}


def project() -> Path:
    root = Path(tempfile.mkdtemp(prefix="pl-worklog-"))
    (root / "board.json").write_text(json.dumps(BOARD, indent=2) + "\n", encoding="utf-8")
    (root / "runs").mkdir()
    (root / "runs" / "T-01.json").write_text(json.dumps({
        "task": "T-01", "state": "done", "attempt": 1,
        "attempts": [{"n": 1, "started": "2026-10-29T10:00:00+00:00",
                      "ended": "2026-10-29T11:30:00+00:00", "result": "pass", "note": None}],
        "events": [], "usage": {"s-1": {"tokens": 1200, "source": "claude",
                                        "updated": "2026-10-29T11:00:00+00:00"}},
        "updated": "2026-10-29T11:30:00+00:00"}, indent=2) + "\n", encoding="utf-8")
    evidence = root / "reviews" / "evidence"
    evidence.mkdir(parents=True)
    log = evidence / "T-01-tests-20261029T110000Z.log"
    log.write_text("$ pytest\nok\n", encoding="utf-8")
    (evidence / "T-01-tests-20261029T110000Z.json").write_text(json.dumps({
        "task": "T-01", "gate": "tests", "command": "pytest", "exit_code": 0, "result": "pass",
        "slot": None, "exclusive": [], "lock_wait_s": 0, "lock_warning": None,
        "started": "2026-10-29T10:50:00+00:00", "finished": "2026-10-29T10:52:00+00:00",
        "commit": None, "dirty": False, "log": log.name,
        "log_sha256": __import__("hashlib").sha256(log.read_bytes()).hexdigest()}, indent=2) + "\n",
        encoding="utf-8")
    folder = runtime.runtime_dir(root) / "sessions" / "s-1"
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps({
        "id": "s-1", "task": "T-01", "role": "worker", "status": "done",
        "provider": "claude", "started": "2026-10-29T10:00:00+00:00",
        "ended": "2026-10-29T10:45:00+00:00", "tokens": 1200}, indent=2) + "\n",
        encoding="utf-8")
    return root


class WorklogTest(unittest.TestCase):
    def test_task_worklog(self) -> None:
        root = project()
        report = worklog.task_worklog(root, "T-01", task=BOARD["tasks"][0])
        self.assertEqual(report["totals"]["sessions"], 1)
        self.assertEqual(report["totals"]["gates"], 1)
        self.assertEqual(report["totals"]["session_seconds"], 2700.0)
        self.assertEqual(report["totals"]["gate_seconds"], 120.0)
        self.assertEqual(report["totals"]["tokens"], 1200)
        self.assertEqual(report["estimate_hours"], 1.0)
        self.assertEqual(report["actual_hours"], 0.75)
        self.assertEqual(report["delta_hours"], -0.25)

    def test_project_worklog(self) -> None:
        root = project()
        report = worklog.project_worklog(root, BOARD["tasks"])
        self.assertEqual(report["totals"]["tasks"], 1)
        self.assertEqual(report["totals"]["actual_hours"], 0.75)
        self.assertEqual(report["totals"]["tokens"], 1200)
        self.assertEqual(report["stages"][0]["tasks"], 1)
        self.assertEqual(report["tasks"][0]["id"], "T-01")


if __name__ == "__main__":
    unittest.main()
