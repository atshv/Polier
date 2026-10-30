"""Guided first-run setup (2.7): state, provider probes and /api/setup."""
from __future__ import annotations

import json
import subprocess
import unittest
import urllib.error
import urllib.request

from dash_helpers import sample_project

from core import runtime, setup
from core.errors import PolierError
from server.app import DashboardApp, DashboardServer

ACTION = {"X-Polier-Action": "1"}
SIGNED_IN = '{"loggedIn": true, "authMethod": "claude.ai"}'


def request(base, path, method="GET", body=None, headers=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


class Probe:
    """A fake ``which``/``run`` pair that records what the probe asked for."""

    def __init__(self, path=None, result=None, error=None) -> None:
        self.path = path
        self.result = result
        self.error = error
        self.calls = []

    def which(self, name):
        self.calls.append(("which", name))
        return self.path

    def run(self, argv, timeout):
        self.calls.append(("run", list(argv), timeout))
        if self.error is not None:
            raise self.error
        return self.result


def provider_keys():
    return {"id", "command", "model", "installed", "path", "signed_in",
            "auth_method", "login_command", "models"}


class SetupStateTest(unittest.TestCase):
    def test_read_defaults_to_pending(self) -> None:
        for config in (None, {}, {"setup": None}, {"setup": "done"}, {"setup": {}}):
            value = setup.read(config)
            self.assertEqual(value, {"version": 1, "status": "pending", "updated_at": None}, config)

    def test_read_preserves_known_status(self) -> None:
        for status in ("done", "skipped", "pending"):
            value = setup.read({"setup": {"version": 1, "status": status,
                                          "updated_at": "2026-01-02T03:04:05Z"}})
            self.assertEqual(value["status"], status)
            self.assertEqual(value["updated_at"], "2026-01-02T03:04:05Z")
            self.assertEqual(value["version"], 1)

    def test_read_invalid_status_is_pending(self) -> None:
        value = setup.read({"setup": {"status": "bogus", "updated_at": 7}})
        self.assertEqual(value["status"], "pending")
        self.assertIsNone(value["updated_at"])

    def test_mark_sets_status_and_time(self) -> None:
        config = {}
        for action, expected in (("complete", "done"), ("skip", "skipped"), ("reset", "pending")):
            record = setup.mark(config, action)
            self.assertEqual(record["status"], expected, action)
            self.assertEqual(record["version"], 1)
            self.assertTrue(record["updated_at"].endswith("Z"), record)
            self.assertIs(config["setup"], record)
            self.assertEqual(setup.read(config)["status"], expected)

    def test_mark_rejects_unknown_action(self) -> None:
        config = {}
        for action in ("bogus", ""):
            with self.assertRaises(PolierError):
                setup.mark(config, action)
        self.assertNotIn("setup", config)


class ProviderStatusTest(unittest.TestCase):
    def test_claude_signed_in(self) -> None:
        probe = Probe(path="/usr/local/bin/claude", result=(0, SIGNED_IN, ""))
        value = setup.provider_status({}, which=probe.which, run=probe.run)
        self.assertEqual(value["id"], "claude")
        self.assertEqual(value["command"], ["claude"])
        self.assertIsNone(value["model"])
        self.assertTrue(value["installed"])
        self.assertEqual(value["path"], "/usr/local/bin/claude")
        self.assertIs(value["signed_in"], True)
        self.assertEqual(value["auth_method"], "claude.ai")
        self.assertEqual(value["login_command"], "claude auth login")
        self.assertEqual(value["models"], ["opus", "sonnet", "haiku"])
        self.assertIn(("run", ["claude", "auth", "status"], 8), probe.calls)

    def test_claude_not_installed_does_not_run(self) -> None:
        probe = Probe(path=None, result=(0, SIGNED_IN, ""))
        value = setup.provider_status({}, which=probe.which, run=probe.run)
        self.assertFalse(value["installed"])
        self.assertIsNone(value["path"])
        self.assertIsNone(value["signed_in"])
        self.assertIsNone(value["auth_method"])
        self.assertEqual([call[0] for call in probe.calls], ["which"])

    def test_custom_command_is_not_probed(self) -> None:
        probe = Probe(path="/opt/bin/my-agent", result=(0, SIGNED_IN, ""))
        config = {"session": {"provider": "custom",
                              "command": ["my-agent", "--json"], "model": "opus"}}
        value = setup.provider_status(config, which=probe.which, run=probe.run)
        self.assertEqual(value["id"], "custom")
        self.assertEqual(value["command"], ["my-agent", "--json"])
        self.assertEqual(value["model"], "opus")
        self.assertTrue(value["installed"])
        self.assertIsNone(value["signed_in"])
        self.assertIsNone(value["auth_method"])
        self.assertIsNone(value["login_command"])
        self.assertEqual(value["models"], [])
        self.assertEqual([call[0] for call in probe.calls], ["which"])

    def test_a_broken_path_lookup_reads_as_not_installed(self) -> None:
        def broken(name):
            raise OSError("PATH is unreadable")

        value = setup.provider_status({}, which=broken, run=lambda argv, timeout: (0, SIGNED_IN, ""))
        self.assertFalse(value["installed"])
        self.assertIsNone(value["path"])
        self.assertIsNone(value["signed_in"])

    def test_failed_probe_reads_as_unknown(self) -> None:
        cases = [
            (0, "not json", ""),
            (0, '["loggedIn"]', ""),
            (0, '{"authMethod": "claude.ai"}', ""),
            (0, "", ""),
            (1, "sign-in required", ""),
        ]
        for result in cases:
            probe = Probe(path="/usr/local/bin/claude", result=result)
            value = setup.provider_status({}, which=probe.which, run=probe.run)
            self.assertIsNone(value["signed_in"], result)
            self.assertIsNone(value["auth_method"], result)
        probe = Probe(path="/usr/local/bin/claude", error=subprocess.TimeoutExpired(["claude"], 8))
        value = setup.provider_status({}, which=probe.which, run=probe.run)
        self.assertIsNone(value["signed_in"])
        self.assertIsNone(value["auth_method"])

    def test_nonzero_exit_with_a_valid_answer_still_counts(self) -> None:
        probe = Probe(path="/usr/local/bin/claude", result=(1, '{"loggedIn": false}', ""))
        value = setup.provider_status({}, which=probe.which, run=probe.run)
        self.assertIs(value["signed_in"], False)
        self.assertIsNone(value["auth_method"])
        probe = Probe(path="/usr/local/bin/claude", result=(1, SIGNED_IN, ""))
        value = setup.provider_status({}, which=probe.which, run=probe.run)
        self.assertIs(value["signed_in"], True)
        self.assertEqual(value["auth_method"], "claude.ai")

    def test_logged_out_is_false(self) -> None:
        probe = Probe(path="/usr/local/bin/claude", result=(0, '{"loggedIn": false}', ""))
        value = setup.provider_status({}, which=probe.which, run=probe.run)
        self.assertIs(value["signed_in"], False)
        self.assertIsNone(value["auth_method"])

    def test_payload_shape(self) -> None:
        probe = Probe(path="/usr/local/bin/claude", result=(0, SIGNED_IN, ""))
        value = setup.payload(board_present=True, config={}, which=probe.which, run=probe.run)
        self.assertEqual(set(value), {"state", "provider", "providers", "board_present"})
        self.assertEqual(value["state"]["status"], "pending")
        self.assertIs(value["board_present"], True)
        self.assertEqual(set(value["provider"]), provider_keys())
        ids = [provider["id"] for provider in value["providers"]]
        self.assertIn("claude", ids)
        self.assertIn("custom", ids)
        for provider in value["providers"]:
            self.assertEqual(set(provider),
                             {"id", "label", "command", "login_command", "models", "hint"})


class SetupInitialTest(unittest.TestCase):
    def test_a_new_machine_starts_pending(self) -> None:
        self.assertEqual(setup.initial(False), {"version": 1, "status": "pending", "updated_at": None})

    def test_an_existing_runtime_counts_as_skipped(self) -> None:
        self.assertEqual(setup.initial(True), {"version": 1, "status": "skipped", "updated_at": None})


class SetupApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_project()
        self.app = DashboardApp(self.root, host="127.0.0.1", port=0, quiet=True)
        self.server = DashboardServer(self.app, port=0).start()
        self.base = f"http://127.0.0.1:{self.app.port}"

    def tearDown(self) -> None:
        self.server.shutdown()

    def saved_config(self):
        path = runtime.runtime_dir(self.root) / "config.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_get_setup(self) -> None:
        status, value = request(self.base, "/api/setup")
        self.assertEqual(status, 200, value)
        self.assertEqual(set(value), {"state", "provider", "providers", "board_present"})
        self.assertEqual(value["state"]["status"], "pending")
        self.assertIsNone(value["state"]["updated_at"])
        self.assertIs(value["board_present"], True)
        self.assertEqual(set(value["provider"]), provider_keys())
        self.assertIsInstance(value["provider"]["installed"], bool)
        self.assertIn(value["provider"]["signed_in"], (True, False, None))
        self.assertIn(value["provider"]["id"], ("claude", "custom"))
        ids = [provider["id"] for provider in value["providers"]]
        self.assertIn("claude", ids)
        self.assertIn("custom", ids)

    def test_config_view_contains_setup(self) -> None:
        status, value = request(self.base, "/api/config")
        self.assertEqual(status, 200, value)
        self.assertEqual(value["setup"]["status"], "pending")
        self.assertEqual(value["setup"]["version"], 1)

    def test_post_requires_action_header(self) -> None:
        status, value = request(self.base, "/api/setup", "POST", {"action": "complete"})
        self.assertEqual(status, 403, value)

    def test_complete_is_saved(self) -> None:
        status, value = request(self.base, "/api/setup", "POST", {"action": "complete"}, ACTION)
        self.assertEqual(status, 200, value)
        self.assertEqual(value["state"]["status"], "done")
        self.assertTrue(value["state"]["updated_at"].endswith("Z"), value)
        self.assertEqual(self.saved_config()["setup"]["status"], "done")
        status, again = request(self.base, "/api/setup")
        self.assertEqual(status, 200)
        self.assertEqual(again["state"]["status"], "done")

    def test_skip_and_reset(self) -> None:
        status, value = request(self.base, "/api/setup", "POST", {"action": "skip"}, ACTION)
        self.assertEqual(status, 200, value)
        self.assertEqual(value["state"]["status"], "skipped")
        status, value = request(self.base, "/api/setup", "POST", {"action": "reset"}, ACTION)
        self.assertEqual(status, 200, value)
        self.assertEqual(value["state"]["status"], "pending")
        self.assertEqual(self.saved_config()["setup"]["status"], "pending")

    def test_unknown_action_is_400(self) -> None:
        status, value = request(self.base, "/api/setup", "POST", {"action": "bogus"}, ACTION)
        self.assertEqual(status, 400, value)
        self.assertIn("unknown setup action", value["error"])

    def test_missing_action_is_400(self) -> None:
        status, value = request(self.base, "/api/setup", "POST", {}, ACTION)
        self.assertEqual(status, 400, value)
        self.assertEqual(value["error"], "action is required")

    def test_read_only_refuses_post(self) -> None:
        app = DashboardApp(self.root, host="127.0.0.1", port=0, quiet=True, read_only=True)
        server = DashboardServer(app, port=0).start()
        base = f"http://127.0.0.1:{app.port}"
        try:
            status, _ = request(base, "/api/setup", "POST", {"action": "complete"}, ACTION)
            self.assertEqual(status, 403)
            status, value = request(base, "/api/setup")
            self.assertEqual(status, 200, value)
            self.assertEqual(value["state"]["status"], "pending")
        finally:
            server.shutdown()

    def test_existing_runtime_without_setup_reads_skipped(self) -> None:
        runtime.write_json(runtime.runtime_dir(self.root) / "config.json",
                           {"version": 1, "session": {"provider": "claude", "command": ["claude"]}})
        status, value = request(self.base, "/api/setup")
        self.assertEqual(status, 200, value)
        self.assertEqual(value["state"]["status"], "skipped")
        status, config = request(self.base, "/api/config")
        self.assertEqual(status, 200, config)
        self.assertEqual(config["setup"]["status"], "skipped")

    def test_post_preserves_other_config_keys(self) -> None:
        runtime.write_json(runtime.runtime_dir(self.root) / "config.json",
                           {"version": 1, "session": {"provider": "custom", "command": ["my-provider"]},
                            "gate_commands": {"tests": "pytest"}, "ui": {"theme": "dark"}})
        status, value = request(self.base, "/api/setup", "POST", {"action": "complete"}, ACTION)
        self.assertEqual(status, 200, value)
        config = self.saved_config()
        self.assertEqual(config["session"]["provider"], "custom")
        self.assertEqual(config["session"]["command"], ["my-provider"])
        self.assertEqual(config["gate_commands"], {"tests": "pytest"})
        self.assertEqual(config["ui"], {"theme": "dark"})
        self.assertEqual(config["setup"]["status"], "done")

    def test_config_put_preserves_setup(self) -> None:
        status, _ = request(self.base, "/api/setup", "POST", {"action": "complete"}, ACTION)
        self.assertEqual(status, 200)
        status, value = request(self.base, "/api/config", "PUT",
                                {"session": {"model": "sonnet"}}, ACTION)
        self.assertEqual(status, 200, value)
        self.assertEqual(value["setup"]["status"], "done")
        self.assertEqual(self.saved_config()["setup"]["status"], "done")

    def test_setup_feature_is_on_by_default(self) -> None:
        status, value = request(self.base, "/api/settings")
        self.assertEqual(status, 200, value)
        self.assertIs(value["features"]["setup"], True)


if __name__ == "__main__":
    unittest.main()
