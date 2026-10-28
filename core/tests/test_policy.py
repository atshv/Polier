"""core.policy: policy.json rules and the shared decision table (PL-18)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from core import policy
from core.errors import PolierError
from core.paths import CASE_INSENSITIVE
from core.shell import command_segments

from .fixtures import project, task, write_policy

CASES = json.loads((Path(__file__).with_name("policy_cases.json")).read_text(encoding="utf-8"))
DEFAULT_POLICY = dict(CASES["policy"], enabled=True)


def one_rule(case: dict) -> dict:
    """A policy with only the command list and pattern of one shared case."""
    return {"enabled": True, "commands": {case["list"]: [case["pattern"]]}}


class SharedTable(unittest.TestCase):
    """Every case of core/tests/policy_cases.json, the Python/JS contract."""

    def test_path_cases(self):
        for case in CASES["path_cases"]:
            with self.subTest(case["name"]):
                self.assertIs(policy.path_matches(case["pattern"], case["rel"]), case["ok"])

    def test_manifest_cases(self):
        for case in CASES["manifest_cases"]:
            with self.subTest(case["name"]):
                self.assertIs(policy.path_matches(case["pattern"], case["rel"]), case["ok"])

    def test_command_cases(self):
        for case in CASES["command_cases"]:
            with self.subTest(case["name"]):
                denial = policy.command_denial(one_rule(case), case["command"], case["role"])
                self.assertEqual((denial or {}).get("rule"), case["denial"],
                                 (case, denial))

    def test_the_shared_policy_is_valid(self):
        self.assertEqual(policy.policy_errors(CASES["policy"]), [])
        self.assertEqual(policy.policy_errors({"enabled": False}), [])


class Loading(unittest.TestCase):
    def test_absent_policy_disables_every_rule(self):
        root = project([task()], repo=False)
        loaded = policy.load_policy(root)
        self.assertEqual(loaded, {"enabled": False})
        self.assertFalse(policy.enabled(loaded))
        self.assertFalse(policy.action_required(loaded, "new_dependency"))
        self.assertIsNone(policy.protected_match(loaded, ".env"))
        self.assertIsNone(policy.manifest_match(loaded, "package.json"))
        self.assertIsNone(policy.command_denial(loaded, "git push origin main"))
        self.assertEqual(policy.limits(loaded), policy.DEFAULTS["limits"])
        with self.assertRaises(PolierError):
            policy.load_policy(root, strict=True)

    def test_the_defaults_fill_every_missing_key(self):
        root = project([task()], repo=False)
        write_policy(root, {"limits": {"max_attempts_per_task": 5}})
        loaded = policy.load_policy(root)
        self.assertTrue(policy.enabled(loaded))
        self.assertEqual(loaded["version"], 1)
        self.assertEqual(policy.limits(loaded)["max_attempts_per_task"], 5)
        self.assertEqual(policy.limits(loaded)["max_in_progress"],
                         policy.DEFAULTS["limits"]["max_in_progress"])
        self.assertEqual(loaded["checks"], policy.DEFAULTS["checks"])
        self.assertEqual(policy.approver(loaded), "owner")
        self.assertTrue(policy.action_required(loaded, "new_dependency"))
        self.assertFalse(policy.action_required(loaded, "state_override"))
        self.assertEqual(policy.policy_errors(loaded), [])

    def test_a_broken_policy_is_never_silently_ignored(self):
        root = project([task()], repo=False)
        (root / "policy.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(PolierError):
            policy.load_policy(root)
        with self.assertRaises(PolierError):
            policy.load_policy(root, strict=True)
        (root / "policy.json").write_text("[]", encoding="utf-8")
        with self.assertRaises(PolierError):
            policy.load_policy(root)

    def test_strict_validates_the_rules(self):
        root = project([task()], repo=False)
        write_policy(root, {"version": 2})
        loaded = policy.load_policy(root)
        self.assertTrue(policy.policy_errors(loaded))
        with self.assertRaises(PolierError):
            policy.load_policy(root, strict=True)

    def test_enabled(self):
        self.assertFalse(policy.enabled(None))
        self.assertFalse(policy.enabled({}))
        self.assertFalse(policy.enabled({"enabled": False}))
        self.assertTrue(policy.enabled({"enabled": True}))
        self.assertTrue(policy.enabled(DEFAULT_POLICY))


class Validation(unittest.TestCase):
    def errors(self, **section) -> list:
        return policy.policy_errors(dict(DEFAULT_POLICY, **section))

    def test_unknown_keys_are_errors(self):
        self.assertTrue(any("unknown key" in e for e in self.errors(unexpected=True)))
        self.assertTrue(any("unknown key 'deep'" in e
                            for e in self.errors(limits={"deep": 1})))
        self.assertTrue(any("unknown key 'silent'" in e
                            for e in self.errors(checks={"silent": True})))

    def test_limits_are_ints_in_range(self):
        for bad in (0, 11, 2.5, "3", True):
            with self.subTest(bad):
                self.assertTrue(any("limits.max_attempts_per_task" in e
                                    for e in self.errors(limits={"max_attempts_per_task": bad})))
        self.assertTrue(any("limits.max_in_progress" in e
                            for e in self.errors(limits={"max_in_progress": 65})))
        self.assertTrue(any("limits.max_review_rounds" in e
                            for e in self.errors(limits={"max_review_rounds": 21})))

    def test_lists_are_lists_of_non_empty_strings(self):
        for bad in ("git push*", ["git push*", ""], [1], [None]):
            with self.subTest(bad):
                self.assertTrue(any("commands.deny" in e
                                    for e in self.errors(commands={"deny": bad})))
        self.assertTrue(any("protect" in e or "protected" in e
                            for e in self.errors(scope={"protected_paths": "x"})))
        self.assertTrue(any("manifests" in e
                            for e in self.errors(dependencies={"manifests": [None]})))
        self.assertTrue(any("approvals.actions" in e
                            for e in self.errors(approvals={"actions": [""]})))

    def test_approval_actions_and_approver(self):
        self.assertTrue(any("unknown action" in e
                            for e in self.errors(approvals={"actions": ["teleport"]})))
        self.assertTrue(any("approver" in e
                            for e in self.errors(approvals={"approver": ""})))

    def test_checks_are_booleans(self):
        self.assertTrue(any("checks.review_before_done" in e
                            for e in self.errors(checks={"review_before_done": "yes"})))
        self.assertTrue(any("dependencies.approval" in e
                            for e in self.errors(dependencies={"approval": 1})))

    def test_a_non_object_policy(self):
        self.assertEqual(policy.policy_errors(None),
                         ["policy.json: the policy must be a JSON object"])


class Paths(unittest.TestCase):
    def test_double_star_matches_zero_or_more_segments(self):
        self.assertTrue(policy.path_matches("docs/**/*.md", "docs/readme.md"))
        self.assertTrue(policy.path_matches("docs/**/*.md", "docs/a/b/c.md"))
        self.assertFalse(policy.path_matches("docs/**/*.md", "src/readme.md"))
        self.assertTrue(policy.path_matches("**", "anything/at/all"))
        self.assertTrue(policy.path_matches("a/**/b", "a/b"))

    def test_a_pattern_without_slash_matches_the_basename(self):
        self.assertTrue(policy.path_matches(".env", ".env"))
        self.assertTrue(policy.path_matches(".env", "sub/dir/.env"))
        self.assertFalse(policy.path_matches(".env", "sub/dir/.env.example"))
        self.assertFalse(policy.path_matches("secrets/**", "sub/secrets/key"))

    def test_case_follows_the_file_system(self):
        self.assertIs(policy.path_matches(".ENV", ".env"), CASE_INSENSITIVE)
        self.assertIs(policy.path_matches("secrets/**", "Secrets/key"), CASE_INSENSITIVE)

    def test_protected_and_manifest_match(self):
        self.assertEqual(policy.protected_match(DEFAULT_POLICY, "apps/web/.env"), ".env")
        self.assertEqual(policy.protected_match(DEFAULT_POLICY, "certs/ca.pem"), "**/*.pem")
        self.assertIsNone(policy.protected_match(DEFAULT_POLICY, "src/app.py"))
        self.assertEqual(policy.manifest_match(DEFAULT_POLICY, "apps/web/package.json"),
                         "package.json")
        self.assertIsNone(policy.manifest_match(DEFAULT_POLICY, "package-lock.json"))

    def test_glob_match_is_case_insensitive_everywhere(self):
        self.assertTrue(policy.glob_match("git push*", "GIT PUSH origin main"))
        self.assertTrue(policy.glob_match("*tools/state.py set*", "python3 TOOLS/STATE.PY SET M01"))
        self.assertFalse(policy.glob_match("git push*", "git status"))
        self.assertFalse(policy.glob_match(None, "git push"))


class Commands(unittest.TestCase):
    def test_deny_blocks_every_role_and_lead_only_the_worker(self):
        self.assertEqual(policy.command_denial(DEFAULT_POLICY, "git push --force", "lead")["rule"],
                         "deny")
        lead_only = policy.command_denial(
            DEFAULT_POLICY, "python3 tools/state.py set M01 in_progress", "worker")
        self.assertEqual(lead_only["rule"], "lead_only")
        self.assertEqual(lead_only["pattern"], "*tools/state.py set*")
        self.assertEqual(lead_only["command"], "python3 tools/state.py set M01 in_progress")
        self.assertTrue(lead_only["reason"])
        self.assertIsNone(policy.command_denial(
            DEFAULT_POLICY, "python3 tools/state.py set M01 in_progress", "lead"))
        self.assertIsNone(policy.command_denial(
            DEFAULT_POLICY, "python3 tools/state.py set M01 in_progress", "off"))
        self.assertIsNone(policy.command_denial(DEFAULT_POLICY, "", "worker"))

    def test_text_in_quotes_and_heredocs_is_data(self):
        payloads = (
            'echo "git push origin main"',
            "rg 'git push' docs",
            "cat <<EOF\ngit push origin main\nEOF",
        )
        for command in payloads:
            with self.subTest(command):
                self.assertIsNone(policy.command_denial(DEFAULT_POLICY, command, "worker"))

    def test_wrappers_nested_shells_and_second_segments(self):
        cases = (
            "sudo env FOO=1 git push origin main",
            "sudo -u root git push origin main",
            "env -u GIT_SSH npm publish",
            "cd /tmp && npm publish",
            "bash -c 'git push origin main'",
            "sh -c \"cd /tmp && npm publish\"",
            "echo hi | xargs true; echo done\nnpm publish",
        )
        for command in cases:
            with self.subTest(command):
                denial = policy.command_denial(DEFAULT_POLICY, command, "worker")
                self.assertIsNotNone(denial, command)

    def test_command_segments_helper(self):
        self.assertEqual(command_segments("cd /tmp && npm publish"),
                         ["cd /tmp", "npm publish"])
        self.assertEqual(command_segments("bash -c 'git push origin main'"),
                         ["git push origin main"])
        self.assertEqual(command_segments("sudo -u root git push origin main"),
                         ["git push origin main"])
        self.assertEqual(command_segments("echo 'npm publish'"), ["echo npm publish"])
        self.assertEqual(command_segments(""), [])
        self.assertEqual(command_segments('echo "open'), ['echo "open'])

    def test_no_command_rule_fires_when_the_policy_is_off(self):
        disabled = {"enabled": False}
        for case in CASES["command_cases"]:
            self.assertIsNone(policy.command_denial(one_rule(case) | {"enabled": False},
                                                    case["command"], case["role"]))


if __name__ == "__main__":
    unittest.main()
