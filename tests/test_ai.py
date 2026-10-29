"""2.5 AI layer: skills, agent profiles, MCP connectors, sessions with an agent, GitHub login."""
from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from dash_helpers import PACKAGE, sample_project

from core import agents, github, mcp_connectors, skills
from core.errors import PolierError
from server.app import DashboardApp, DashboardServer
from server.sessions import SessionManager

FAKE_PROVIDER = '''\
import json
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "ok"}), flush=True)
'''

FAKE_GH = '''#!/bin/sh
state="$(dirname "$0")/logged-in"
case "$1 $2" in
  "auth login")
    case " $* " in
      *" --web "*)
        echo "! First copy your one-time code: WXYZ-1234"
        read line
        touch "$state"; echo "Authentication complete."; exit 0 ;;
    esac
    read token; touch "$state"; exit 0 ;;
  "auth status")
    if [ -f "$state" ]; then
      printf "github.com\\n  Logged in to github.com account octocat (keyring)\\n  - Token scopes: 'gist', 'read:org', 'repo'\\n"; exit 0
    fi
    echo "You are not logged into any GitHub hosts." >&2; exit 1 ;;
  "auth logout") rm -f "$state"; exit 0 ;;
esac
exit 1
'''


def request(base, path, method="GET", body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if method != "GET":
        req.add_header("X-Polier-Action", "1")
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


class SkillsTest(unittest.TestCase):
    def test_save_load_and_delete_in_the_agent_skills_layout(self) -> None:
        root = sample_project()
        saved = skills.save(root, "api-style", {"name": "API style", "description": "Use when adding an endpoint.",
                                                "body": "Return JSON errors."})
        self.assertEqual(saved["path"], ".claude/skills/api-style/SKILL.md")
        text = (root / saved["path"]).read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: API style\ndescription: Use when adding an endpoint.\n---"))
        self.assertEqual([skill["id"] for skill in skills.load_all(root)], ["api-style"])
        skills.delete(root, "api-style")
        self.assertEqual(skills.load_all(root), [])

    def test_validation(self) -> None:
        root = sample_project()
        with self.assertRaises(PolierError):
            skills.save(root, "Bad Id", {"name": "x", "description": "y", "body": "z"})
        with self.assertRaises(PolierError):
            skills.save(root, "no-description", {"name": "x", "description": "", "body": "z"})

    def test_examples_install_once(self) -> None:
        root = sample_project()
        examples = skills.examples(PACKAGE)
        self.assertGreaterEqual(len(examples), 5)
        self.assertTrue(all(skill["description"] for skill in examples))
        first = skills.install_examples(root, PACKAGE)
        self.assertEqual(sorted(first), sorted(skill["id"] for skill in examples))
        self.assertEqual(skills.install_examples(root, PACKAGE), [])

    def test_prompt_section_inlines_the_body(self) -> None:
        section = skills.prompt_section([{"name": "A", "description": "when a", "body": "do a"}])
        self.assertIn("## Skills", section)
        self.assertIn("do a", section)


class AgentsTest(unittest.TestCase):
    def test_builtin_profiles_without_a_file(self) -> None:
        value = agents.load(sample_project())
        self.assertTrue(value["builtin"])
        self.assertEqual([agent["role"] for agent in value["agents"]], ["worker", "reviewer", "lead"])
        example_ids = {skill["id"] for skill in skills.examples(PACKAGE)}
        for agent in value["agents"]:
            self.assertTrue(set(agent["skills"]) <= example_ids, agent["id"])

    def test_save_validates_and_writes_agents_json(self) -> None:
        root = sample_project()
        with self.assertRaises(PolierError):
            agents.save(root, [{"id": "x", "name": "X", "role": "boss"}])
        with self.assertRaises(PolierError):
            agents.save(root, [{"id": "a", "name": "A", "role": "worker"}, {"id": "a", "name": "B", "role": "lead"}])
        value = agents.save(root, [{"id": "ui", "name": "UI builder", "role": "worker", "skills": ["test-first"],
                                    "instructions": "Follow docs/design-rules.md."}])
        self.assertFalse(value["builtin"])
        self.assertTrue((root / "agents.json").is_file())
        options = agents.session_options(agents.get(root, "ui"),
                                         [{"name": "T", "description": "d", "body": "b"}], "focus")
        self.assertEqual(options["role"], "worker")
        self.assertIn("design-rules", options["note"])
        self.assertIn("## Operator note", options["note"])


class ConnectorsTest(unittest.TestCase):
    def test_upsert_masks_and_keeps_secrets(self) -> None:
        config = mcp_connectors.upsert({}, "remote", {"type": "http", "url": "https://example.com/mcp",
                                                       "headers": {"Authorization": "Bearer secret"}})
        view = mcp_connectors.view(config, PACKAGE, "/project")
        remote = next(entry for entry in view["connectors"] if entry["name"] == "remote")
        self.assertEqual(remote["headers"]["Authorization"], mcp_connectors.MASK)
        self.assertNotIn("secret", json.dumps(view))
        config = mcp_connectors.upsert(config, "remote", {"type": "http", "url": "https://example.com/mcp",
                                                          "headers": {"Authorization": mcp_connectors.MASK}})
        self.assertEqual(config["mcp_servers"]["remote"]["headers"]["Authorization"], "Bearer secret")

    def test_validation(self) -> None:
        for name, entry in (("polier", {"command": "x"}), ("Bad", {"command": "x"}),
                            ("x", {"type": "stdio"}), ("y", {"type": "http", "url": "ftp://x"}),
                            ("z", {"command": "x", "roles": ["admin"]})):
            with self.assertRaises(PolierError, msg=name):
                mcp_connectors.upsert({}, name, entry)

    def test_session_selection_by_role_and_agent(self) -> None:
        config = mcp_connectors.upsert({}, "files", {"command": "npx", "args": ["fs"], "roles": ["worker"]})
        config = mcp_connectors.upsert(config, "off", {"command": "x", "enabled": False})
        worker = mcp_connectors.for_session(config, "worker", PACKAGE, "/p")
        self.assertEqual(sorted(worker), ["files", "polier"])
        self.assertIn("--read-only", worker["polier"]["args"])
        self.assertEqual(sorted(mcp_connectors.for_session(config, "reviewer", PACKAGE, "/p")), ["polier"])
        self.assertEqual(sorted(mcp_connectors.for_session(config, "worker", PACKAGE, "/p", ["files"])), ["files"])
        config = mcp_connectors.upsert(config, "polier", {"enabled": False})
        self.assertEqual(sorted(mcp_connectors.for_session(config, "worker", PACKAGE, "/p")), ["files"])

    def test_the_builtin_server_answers_a_handshake(self) -> None:
        result = mcp_connectors.test({}, "polier", PACKAGE, sample_project())
        self.assertTrue(result["ok"], result)
        self.assertIn("polier_snapshot", result["tools"])

    def test_a_missing_command_is_reported(self) -> None:
        config = mcp_connectors.upsert({}, "ghost", {"command": "polier-no-such-command"})
        self.assertFalse(mcp_connectors.test(config, "ghost", PACKAGE, "/p")["ok"])


class SessionWithConnectorsTest(unittest.TestCase):
    def test_mcp_config_and_allowed_tools_reach_the_provider(self) -> None:
        root = sample_project()
        fake = root / "fake_claude.py"
        fake.write_text(FAKE_PROVIDER, encoding="utf-8")
        manager = SessionManager(root, bus=None, package_root=PACKAGE, config={
            "command": [sys.executable, str(fake)], "allowed_tools": ["Read"], "permission_mode": None,
            "timeout_s": 30, "max_concurrent": 2})
        connectors = {"files": {"command": "npx", "args": ["fs"]}}
        session = manager.start(task="F-01", role="worker", addendum="## Agent: Builder", agent="builder",
                                connectors=connectors)
        deadline = time.time() + 30
        while manager.get(session["id"])["status"] in ("starting", "running") and time.time() < deadline:
            time.sleep(0.05)
        view = manager.get(session["id"])
        self.assertEqual(view["status"], "done", view)
        self.assertEqual(view["connectors"], ["files"])
        self.assertIn("## Agent: Builder", view["prompt"])
        command = next(line for line in view["lines"] if line.startswith("$ "))
        self.assertIn("--mcp-config", command)
        self.assertIn("Read mcp__files", command)
        written = json.loads((Path(view["folder"]) / "mcp.json").read_text(encoding="utf-8"))
        self.assertEqual(written, {"mcpServers": connectors})


class AiRoutesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_project()
        self.app = DashboardApp(self.root, host="127.0.0.1", port=0, quiet=True)
        self.server = DashboardServer(self.app, port=0).start()
        self.base = f"http://127.0.0.1:{self.app.port}"

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_agents_skills_and_mcp(self) -> None:
        status, value = request(self.base, "/api/agents")
        self.assertEqual(status, 200)
        self.assertTrue(value["builtin"])
        self.assertEqual(value["agents"][0]["missing_skills"], [])
        status, value = request(self.base, "/api/agents", "PUT",
                                {"agents": [{"id": "solo", "name": "Solo", "role": "lead"}]})
        self.assertEqual(status, 200, value)
        self.assertEqual([agent["id"] for agent in value["agents"]], ["solo"])
        status, _ = request(self.base, "/api/agents", "PUT", {"agents": [{"id": "x", "name": "X", "role": "boss"}]})
        self.assertEqual(status, 400)

        status, value = request(self.base, "/api/skills/examples", "POST", {"ids": ["test-first"]})
        self.assertEqual((status, value["installed"]), (200, ["test-first"]))
        status, value = request(self.base, "/api/skills/mine", "PUT",
                                {"name": "Mine", "description": "Use always.", "body": "Be brief."})
        self.assertEqual(status, 200, value)
        status, value = request(self.base, "/api/skills")
        self.assertEqual(sorted(skill["id"] for skill in value["skills"]), ["mine", "test-first"])
        self.assertEqual(request(self.base, "/api/skills/mine", "DELETE")[0], 200)

        status, value = request(self.base, "/api/mcp")
        self.assertEqual(status, 200)
        self.assertIn("polier_snapshot", [tool["name"] for tool in value["server"]["tools"]])
        status, value = request(self.base, "/api/mcp/connectors/docs", "PUT",
                                {"type": "http", "url": "https://example.com/mcp", "headers": {"X-Key": "k"}})
        self.assertEqual(status, 200, value)
        self.assertNotIn('"k"', json.dumps(value))
        self.assertEqual(request(self.base, "/api/mcp/connectors/docs", "DELETE")[0], 200)
        self.assertEqual(request(self.base, "/api/mcp/connectors/docs", "DELETE")[0], 404)

    def test_session_with_an_unknown_agent_is_refused(self) -> None:
        status, value = request(self.base, "/api/sessions", "POST", {"agent": "nobody", "task": "F-01"})
        self.assertEqual(status, 404, value)


@unittest.skipIf(os.name != "posix", "the fake gh is a shell script")
class GithubLoginTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp())
        script = self.folder / "gh"
        script.write_text(FAKE_GH, encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        self.saved = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{self.folder}{os.pathsep}{self.saved}"
        self.saved_token = {key: os.environ.pop(key) for key in ("GH_TOKEN", "GITHUB_TOKEN") if key in os.environ}

    def tearDown(self) -> None:
        os.environ["PATH"] = self.saved
        os.environ.update(self.saved_token)

    def test_device_flow_token_and_logout(self) -> None:
        self.assertFalse(github.auth_status()["logged_in"])
        login = github.DeviceLogin()
        state = login.start()
        self.assertEqual((state["status"], state["code"]), ("waiting", "WXYZ-1234"))
        deadline = time.time() + 10
        while login.view()["status"] == "waiting" and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual(login.view()["status"], "done")
        status = github.auth_status()
        self.assertEqual((status["logged_in"], status["user"]), (True, "octocat"))
        self.assertIn("repo", status["scopes"])
        self.assertFalse(github.logout()["logged_in"])
        with self.assertRaises(PolierError):
            github.login_with_token("not a token")
        self.assertTrue(github.login_with_token("ghp_" + "a" * 36)["logged_in"])


if __name__ == "__main__":
    unittest.main()
