"""tools/dispatch.py: the text plan, the JSON plan and the --limit option."""
from __future__ import annotations

import json
import unittest

from core import approvals, claims, runs
from core.dispatch import plan

from helpers import make_project, run_tool, task


def write_policy(root, extra: dict | None = None) -> None:
    data = {"version": 1}
    data.update(extra or {})
    (root / "policy.json").write_text(json.dumps(data), encoding="utf-8")


def briefs(root, *task_ids: str) -> None:
    folder = root / "tasks"
    folder.mkdir(exist_ok=True)
    for task_id in task_ids:
        (folder / f"{task_id}.md").write_text(f"# {task_id}\n", encoding="utf-8")


def run(root, *args):
    return run_tool("dispatch.py", *args, "--root", str(root))


class Text(unittest.TestCase):
    def fixture(self):
        root = make_project([
            task("M00", status="in_progress"),
            task("M01", status="pending", parallel_group="db", scope_write=["src/db/"]),
            task("M02", status="pending", parallel_group="db", scope_write=["src/api/"]),
            task("M03", status="pending"),
            task("M04", status="pending", depends_on=["M02"]),
        ])
        write_policy(root)
        briefs(root, "M01", "M02", "M03", "M04")
        runs.start_attempt(root, "M00")
        runs.start_attempt(root, "M00")
        approvals.request(root, "new_dependency", "M03")
        return root

    def test_the_text_plan_has_every_section(self):
        root = self.fixture()
        result = run(root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = result.stdout
        for section in ("DISPATCH t (profile S)",
                        "Limits: max_attempts_per_task 3 · max_in_progress 2",
                        "Running:", "Next wave:", "Later waves:", "Blocked:",
                        "Conflicts:", "Pending approvals:"):
            self.assertIn(section, output)
        self.assertIn("M00 Task M00 — in_progress · attempt 2/3", output)
        self.assertIn("M01", output)
        self.assertIn("Next: M01, M02", output)
        self.assertIn("M03", output)
        self.assertIn("M04: waits for M02", output)
        self.assertIn("action: python3 tools/state.py show M02 --json", output)
        self.assertIn("AP-001 new_dependency for M03", output)

    def test_a_claimed_task_is_shown_as_running_with_its_session(self):
        root = make_project([task("M01", status="pending")])
        write_policy(root)
        briefs(root, "M01")
        claims.take(root, "M01", harness="dsh", session="session-7")
        result = run(root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("M01 Task M01 — pending · attempt 0/3 · claim dsh/session-7",
                      result.stdout)
        self.assertIn("Next wave:\n  none", result.stdout)

    def test_conflicts_and_attempt_exhaustion_are_printed_with_actions(self):
        root = make_project([
            task("M01", status="pending", parallel_group="db", scope_write=["src/db/"]),
            task("M02", status="pending", parallel_group="db", scope_write=["src/db/x.py"]),
            task("M03", status="pending"),
        ])
        write_policy(root, {"limits": {"max_in_progress": 3}})
        briefs(root, "M01", "M02", "M03")
        for _ in range(3):
            runs.start_attempt(root, "M03")
            runs.finish_attempt(root, "M03", "fail")
        result = run(root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("M01 / M02: src/db/, src/db/x.py", result.stdout)
        self.assertIn("M03: attempts 3/3 used — escalate", result.stdout)
        self.assertIn("action: python3 tools/state.py set M03 blocked", result.stdout)

    def test_without_a_policy_the_attempt_limit_does_not_block(self):
        root = make_project([task("M01", status="pending")])
        briefs(root, "M01")
        self.assertFalse((root / "policy.json").exists())
        for _ in range(3):
            runs.start_attempt(root, "M01")
            runs.finish_attempt(root, "M01", "fail")
        result = run(root, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = json.loads(result.stdout)
        self.assertEqual(parsed["blocked"], [])
        self.assertEqual([entry["id"] for entry in parsed["waves"][0]], ["M01"])


class Json(unittest.TestCase):
    def fixture(self):
        root = make_project([
            task("M01", status="pending", parallel_group="g", scope_write=["a/"]),
            task("M02", status="pending", parallel_group="g", scope_write=["b/"]),
        ])
        write_policy(root)
        briefs(root, "M01", "M02")
        return root

    def test_json_prints_the_plan_of_core_dispatch(self):
        root = self.fixture()
        result = run(root, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = json.loads(result.stdout)
        self.assertEqual(parsed, plan(root))
        self.assertEqual(set(parsed), {"project", "profile", "limits", "running", "waves",
                                       "blocked", "conflicts", "approvals_pending", "next"})

    def test_limit_caps_the_tasks_per_wave(self):
        root = self.fixture()
        result = run(root, "--json", "--limit", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = json.loads(result.stdout)
        self.assertEqual([[entry["id"] for entry in wave] for wave in parsed["waves"]],
                         [["M01"], ["M02"]])
        self.assertEqual(parsed["next"], ["M01"])

    def test_a_bad_limit_is_a_usage_error(self):
        root = self.fixture()
        self.assertEqual(run(root, "--limit", "0").returncode, 2)
        self.assertEqual(run(root, "--limit", "x").returncode, 2)


class Errors(unittest.TestCase):
    def test_a_missing_board_is_an_environment_error(self):
        root = make_project([task("M01", status="pending")])
        (root / "board.json").unlink()
        result = run(root)
        self.assertEqual(result.returncode, 2)
        self.assertIn("board.json not found", result.stderr)

    def test_the_text_and_json_forms_stay_read_only(self):
        root = make_project([task("M01", status="pending")])
        write_policy(root)
        briefs(root, "M01")
        before = (root / "board.json").read_text()
        run(root)
        run(root, "--json")
        self.assertEqual((root / "board.json").read_text(), before)
        self.assertFalse((root / "runs").exists())


if __name__ == "__main__":
    unittest.main()
