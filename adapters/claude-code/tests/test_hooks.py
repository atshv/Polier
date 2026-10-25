"""The Claude Code hooks, driven with simulated hook events on throwaway projects.

Run: python3 -m unittest discover -s adapters/claude-code/tests
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

ADAPTER = Path(__file__).resolve().parents[1]
PACKAGE = ADAPTER.parents[1]
sys.path.insert(0, str(ADAPTER))
sys.path.insert(0, str(PACKAGE))

import hook  # noqa: E402
from core.tests.fixtures import git, project, task  # noqa: E402


def pre(root: Path, tool: str, tool_input: dict, cwd: Path = None, **env):
    event = {"session_id": "s1", "hook_event_name": "PreToolUse", "cwd": str(cwd or root),
             "tool_name": tool, "tool_input": tool_input}
    return hook.pre_tool_use(event, env)


def write(root: Path, rel: str, **env):
    return pre(root, "Write", {"file_path": str(root / rel), "content": "x"}, **env)


def bash(root: Path, command: str, cwd: Path = None, **env):
    return pre(root, "Bash", {"command": command}, cwd=cwd, **env)


def stop(root: Path, active: bool = False, session: str = "s1", **env):
    event = {"session_id": session, "hook_event_name": "Stop", "cwd": str(root), "stop_hook_active": active}
    return hook.stop(event, env)


def decision(output):
    return output["hookSpecificOutput"]["permissionDecision"] if output else "allow"


def reason(output):
    return output["hookSpecificOutput"]["permissionDecisionReason"]


class FileTools(unittest.TestCase):
    def test_scope_board_evidence_and_outside(self):
        root = project([task()])
        self.assertIsNone(write(root, "src/app.py"))
        out = write(root, "README.md")
        self.assertEqual(decision(out), "deny")
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertIn("write to README.md blocked, the path is outside the write scope of M01", reason(out))
        self.assertIn("lead-owned", reason(write(root, "board.json")))
        self.assertIsNone(write(root, "reviews/evidence/M01-tests.log"))
        self.assertIn("outside the project", reason(pre(root, "Write", {"file_path": str(root.parent / "x")})))

    def test_every_file_tool(self):
        root = project([task()])
        for tool, key in hook.FILE_TOOLS.items():
            with self.subTest(tool):
                self.assertEqual(decision(pre(root, tool, {key: str(root / "README.md")})), "deny")
                self.assertIsNone(pre(root, tool, {key: str(root / "src/app.py")}))

    def test_relative_path_uses_the_event_cwd(self):
        root = project([task()])
        self.assertIsNone(pre(root, "Edit", {"file_path": "app.py"}, cwd=root / "src"))

    def test_other_tools_and_idle_projects(self):
        root = project([task()])
        self.assertIsNone(pre(root, "Read", {"file_path": str(root / "README.md")}))
        idle = project([task(status="pending")])
        self.assertIsNone(write(idle, "README.md"))
        no_board = project([task()])
        (no_board / "board.json").unlink()
        self.assertIsNone(write(no_board, "README.md"))

    def test_roles(self):
        root = project([task()])
        self.assertIsNone(write(root, "board.json", POLIER_ROLE="lead"))
        self.assertIsNone(write(root, "README.md", POLIER_ROLE="off"))
        self.assertIsNone(write(root, "reviews/M01.md", POLIER_ROLE="reviewer"))
        self.assertIn("reviewer session writes only under reviews/", reason(write(root, "src/app.py", POLIER_ROLE="reviewer")))
        self.assertEqual(decision(write(root, "README.md", POLIER_ROLE="nonsense")), "deny")

    def test_pinned_task(self):
        root = project([task("M01"), task("M02", scope_write=["README.md"])])
        self.assertIsNone(write(root, "README.md"))  # unbound: union of both scopes
        self.assertEqual(decision(write(root, "README.md", POLIER_TASK="m01")), "deny")

    def test_enforce_modes(self):
        root = project([task()])
        self.assertEqual(decision(write(root, "README.md", POLIER_ENFORCE="ask")), "ask")
        self.assertIsNone(write(root, "README.md", POLIER_ENFORCE="off"))


class Bash(unittest.TestCase):
    def test_redirections_and_writers(self):
        root = project([task()])
        self.assertIsNone(bash(root, "echo 'x = 2' > src/app.py"))
        for command in ("echo x > README.md", "echo x >> board.json", "sed -i s/r/R/ README.md",
                        "cp src/app.py README.md", "tee README.md < src/app.py", "touch notes.txt",
                        "bash -c 'echo hi > README.md'", "cat > README.md <<'EOF'\nhello\nEOF"):
            with self.subTest(command):
                out = bash(root, command)
                self.assertEqual(decision(out), "deny")
                self.assertIn("(Bash: ", reason(out))

    def test_cd_is_followed(self):
        root = project([task()])
        self.assertEqual(decision(bash(root, "cd src && echo x > ../README.md")), "deny")
        self.assertIsNone(bash(root, "echo x > app.py", cwd=root / "src"))

    def test_reads_scratch_and_pipelines_pass(self):
        root = project([task()])
        for command in ("cat README.md | grep r", "python3 -m pytest -q > /tmp/out.txt 2>&1",
                        "ls > /dev/null", "git status", "echo hi 2>&1"):
            with self.subTest(command):
                self.assertIsNone(bash(root, command))

    def test_delete_tracked_is_denied_untracked_is_an_undo(self):
        root = project([task()])
        self.assertEqual(decision(bash(root, "rm README.md")), "deny")
        (root / "stray.txt").write_text("made by a script\n")
        self.assertIsNone(bash(root, "rm stray.txt"))
        self.assertEqual(decision(bash(root, "mv README.md src/app.py")), "deny")

    def test_reviewer_bash(self):
        root = project([task()])
        self.assertIsNone(bash(root, "echo ok > reviews/M01.md", POLIER_ROLE="reviewer"))
        self.assertEqual(decision(bash(root, "echo x > src/app.py", POLIER_ROLE="reviewer")), "deny")

    def test_bash_check_can_be_turned_off(self):
        root = project([task()])
        self.assertIsNone(bash(root, "echo x > README.md", POLIER_BASH="0"))

    def test_what_bash_detection_does_not_see(self):
        # Documented in the README: these pass the guard and are left to the stop check.
        root = project([task()])
        for command in ("python3 -c \"open('README.md','w').write('x')\"", "echo x > $TARGET",
                        "git checkout -- README.md", "find . -name '*.md' -delete"):
            with self.subTest(command):
                self.assertIsNone(bash(root, command))


class Stop(unittest.TestCase):
    def test_clean_tree_lets_claude_stop(self):
        root = project([task()])
        (root / "src" / "app.py").write_text("x = 2\n")
        self.assertIsNone(stop(root))

    def test_violation_blocks_up_to_the_reminder_limit(self):
        root = project([task()])
        (root / "README.md").write_text("changed by a script\n")
        first = stop(root)
        self.assertEqual(first["decision"], "block")
        self.assertTrue(first["reason"].startswith("Polier: the working tree has changes outside the scope of M01."))
        self.assertIn("- README.md: outside scope", first["reason"])
        self.assertEqual(stop(root, active=True)["decision"], "block")
        self.assertIsNone(stop(root, active=True))          # gives up after 2 reminders
        self.assertEqual(stop(root)["decision"], "block")   # a new turn counts again
        self.assertIsNone(stop(root, active=True, POLIER_MAX_STOP_REMINDERS="1"))
        self.assertEqual(stop(root, active=True, session="other")["decision"], "block")

    def test_counter_lives_in_the_git_dir(self):
        root = project([task()])
        (root / "README.md").write_text("x\n")
        stop(root)
        self.assertTrue(list((root / ".git" / "polier").glob("claude-code-stop-*.json")))
        result = subprocess.run(["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), "M README.md")

    def test_no_check_for_leads_several_tasks_no_git_or_off(self):
        root = project([task()])
        (root / "README.md").write_text("x\n")
        self.assertIsNone(stop(root, POLIER_ROLE="lead"))
        self.assertIsNone(stop(root, POLIER_STOP_CHECK="0"))
        several = project([task("M01"), task("M02")])
        (several / "README.md").write_text("x\n")
        self.assertIsNone(stop(several))
        no_git = project([task()], repo=False)
        self.assertIsNone(stop(no_git))


class EndToEnd(unittest.TestCase):
    """The script as Claude Code runs it: JSON on stdin, JSON on stdout."""

    def run_hook(self, name: str, event: dict, **env):
        import os
        full_env = {k: v for k, v in os.environ.items() if not k.startswith("POLIER_")}
        full_env.update(env)
        return subprocess.run([sys.executable, str(ADAPTER / "hook.py"), name], input=json.dumps(event),
                              capture_output=True, text=True, env=full_env, check=False)

    def test_pre_tool_use_and_stop(self):
        root = project([task()])
        event = {"session_id": "e2e", "cwd": str(root), "hook_event_name": "PreToolUse",
                 "tool_name": "Write", "tool_input": {"file_path": str(root / "README.md"), "content": "x"}}
        result = self.run_hook("pre-tool-use", event)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

        event["tool_input"]["file_path"] = str(root / "src" / "app.py")
        result = self.run_hook("pre-tool-use", event)
        self.assertEqual((result.returncode, result.stdout), (0, ""))

        (root / "README.md").write_text("x\n")
        result = self.run_hook("stop", {"session_id": "e2e", "cwd": str(root), "hook_event_name": "Stop",
                                        "stop_hook_active": False})
        self.assertEqual(json.loads(result.stdout)["decision"], "block")

    def test_project_dir_fallback(self):
        root = project([task()])
        event = {"tool_name": "Bash", "tool_input": {"command": f"echo x > {root / 'README.md'}"}, "cwd": "/"}
        result = self.run_hook("pre-tool-use", event, CLAUDE_PROJECT_DIR=str(root))
        self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_bad_input_and_usage(self):
        result = self.run_hook("pre-tool-use", {})
        self.assertEqual((result.returncode, result.stdout), (0, ""))
        broken = subprocess.run([sys.executable, str(ADAPTER / "hook.py"), "stop"], input="{nope",
                                capture_output=True, text=True, check=False)
        self.assertEqual(broken.returncode, 0)
        self.assertIn("polier hook:", broken.stderr)
        self.assertEqual(self.run_hook("nonsense", {}).returncode, 1)

    def test_main_in_process(self):
        root = project([task()])
        event = {"cwd": str(root), "tool_name": "Write", "tool_input": {"file_path": str(root / "README.md")}}
        out = io.StringIO()
        old, sys.stdout = sys.stdout, out
        try:
            code = hook.main(["pre-tool-use"], io.StringIO(json.dumps(event)), {})
        finally:
            sys.stdout = old
        self.assertEqual(code, 0)
        self.assertIn('"deny"', out.getvalue())


if __name__ == "__main__":
    unittest.main()


class Claims(unittest.TestCase):
    """PL-04: cross-harness claims taken by PreToolUse when POLIER_TASK is set."""

    def claim_file(self, root: Path, task_id: str = "M01") -> Path:
        return root / ".git" / "polier" / "claims" / f"{task_id}.json"

    def test_polier_task_takes_and_refreshes_the_claim(self):
        root = project([task()])
        self.assertIsNone(write(root, "src/app.py", POLIER_TASK="M01"))
        self.assertTrue(self.claim_file(root).exists())
        claim = json.loads(self.claim_file(root).read_text())
        self.assertEqual((claim["task"], claim["harness"], claim["session"]),
                         ("M01", "claude-code", "s1"))
        self.assertEqual(claim["worktree"], str(root))
        self.assertIsNone(write(root, "src/app.py", POLIER_TASK="M01"))
        self.assertEqual(json.loads(self.claim_file(root).read_text())["started"], claim["started"])

    def test_claim_from_another_harness_denies_and_names_the_holder(self):
        root = project([task()])
        from core.claims import take
        take(root, "M01", harness="dsh", session="agent-1")
        out = write(root, "src/app.py", POLIER_TASK="M01")
        self.assertEqual(decision(out), "deny")
        self.assertIn("dsh", reason(out))
        self.assertIn("agent-1", reason(out))
        self.assertEqual(json.loads(self.claim_file(root).read_text())["session"], "agent-1")

    def test_the_board_is_never_written_by_claims(self):
        root = project([task()])
        before = (root / "board.json").read_text()
        write(root, "src/app.py", POLIER_TASK="M01")
        self.assertEqual((root / "board.json").read_text(), before)

    def test_claims_are_per_repository(self):
        first = project([task()])
        second = project([task()])
        write(first, "src/app.py", POLIER_TASK="M01")
        self.assertIsNone(write(second, "src/app.py", POLIER_TASK="M01"))


class WorktreeRule(unittest.TestCase):
    """PL-05: a bound task with a worktree blocks writes in the main checkout."""

    def test_required_denies_the_main_checkout(self):
        from core.tests.fixtures import set_board
        root = project([task(worktree="/somewhere/repo-M01")])
        set_board(root, profile="M", schema_version="1.0")
        out = write(root, "src/app.py", POLIER_TASK="M01")
        self.assertEqual(decision(out), "deny")
        self.assertIn("work in /somewhere/repo-M01", reason(out))
        self.assertIn("work in /somewhere/repo-M01", reason(bash(root, "echo x > src/app.py")))

    def test_legacy_m_board_defaults_to_recommended(self):
        from core.tests.fixtures import set_board
        root = project([task(worktree="/somewhere/repo-M01")])
        set_board(root, profile="M")  # no schema_version: a 0.9 board
        self.assertIsNone(write(root, "src/app.py", POLIER_TASK="M01"))

    def test_profile_s_defaults_to_off(self):
        root = project([task(worktree="/somewhere/repo-M01")])
        self.assertIsNone(write(root, "src/app.py"))

    def test_evidence_stays_writable(self):
        from core.tests.fixtures import set_board
        root = project([task(worktree="/somewhere/repo-M01")])
        set_board(root, profile="M", schema_version="1.0")
        self.assertIsNone(write(root, "reviews/evidence/M01-tests.log"))


class KillWarning(unittest.TestCase):
    """PL-16: a Bash command that stops processes asks, it never denies."""

    def test_kill_patterns_ask(self):
        root = project([task()])
        for command in ("pkill -f 'next dev'", "kill 123", "killall node",
                        "lsof -ti:3000 | xargs kill -9"):
            with self.subTest(command):
                out = bash(root, command)
                self.assertEqual(decision(out), "ask")
                self.assertIn("do not stop processes you did not start; use your slot's ports",
                              reason(out))

    def test_text_does_not_ask(self):
        root = project([task()])
        for command in ("echo 'pkill -f node'", "grep -rn pkill src/", "cat <<'EOF'\npkill node\nEOF"):
            with self.subTest(command):
                self.assertIsNone(bash(root, command))

    def test_a_write_violation_still_wins(self):
        root = project([task()])
        out = bash(root, "echo x > README.md; pkill -f node")
        self.assertEqual(decision(out), "deny")
        self.assertIn("outside the write scope", reason(out))

    def test_lead_does_not_get_the_warning(self):
        root = project([task()])
        self.assertIsNone(bash(root, "pkill -f node", POLIER_ROLE="lead"))


class ForeignStop(unittest.TestCase):
    """PL-05: foreign changes are listed separately and never block the stop."""

    def setUp(self):
        self.root = project([task("M01"), task("M02", "pending", scope_write=["docs/"])])
        from core.claims import take
        take(self.root, "M02", harness="dsh", session="agent-other")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "x.md").write_text("foreign\n")

    def test_foreign_only_is_reported_but_does_not_block(self):
        out = stop(self.root, POLIER_TASK="M01")
        self.assertIsNotNone(out)
        self.assertNotIn("decision", out)
        self.assertIn("foreign changes (task M02, harness dsh)", out["systemMessage"])

    def test_a_violation_blocks_and_lists_foreign_changes_separately(self):
        (self.root / "README.md").write_text("changed\n")
        out = stop(self.root, POLIER_TASK="M01")
        self.assertEqual(out["decision"], "block")
        self.assertIn("README.md: outside scope", out["reason"])
        self.assertIn("foreign changes (task M02, harness dsh)", out["reason"])
