"""tools/research.py: dependencies, docs/versions.md, registry lookup and research notes."""
from __future__ import annotations

import http.server
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from helpers import run_tool

import research  # noqa: E402

NPM = {
    "left-pad": {"dist-tags": {"latest": "1.3.0"},
                 "versions": {"1.2.0": {}, "1.3.0": {}},
                 "time": {"1.2.0": "2017-01-01T00:00:00Z", "1.3.0": "2018-04-09T00:00:00Z"}},
    "react": {"dist-tags": {"latest": "18.3.1"}, "versions": {"18.3.1": {}},
              "time": {"18.3.1": "2024-04-26T00:00:00Z"}},
}
PYPI = {
    "httpx": {"info": {"version": "0.28.1"},
              "releases": {"0.27.0": [{"upload_time_iso_8601": "2024-02-21T00:00:00Z"}],
                           "0.28.1": [{"upload_time_iso_8601": "2024-12-06T00:00:00Z"}]}},
}


class Registry(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.startswith("/npm/"):
            data = NPM.get(self.path[len("/npm/"):])
        elif self.path.startswith("/pypi/pypi/"):
            data = PYPI.get(self.path.split("/")[3])
        else:
            data = None
        body = json.dumps(data or {"error": "not found"}).encode()
        self.send_response(200 if data else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def project(**files: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix="pl-research-"))
    for rel, text in files.items():
        path = root / rel.replace("__", "/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


PACKAGE_JSON = json.dumps({"dependencies": {"left-pad": "1.2.0", "react": "^18.3.1"},
                           "devDependencies": {"local": "file:../x"}})
VERSIONS = """# Versions: t

| Tool / library | Exact version | Source URL | Date checked | Approved by |
| --- | --- | --- | --- | --- |
| `left-pad` | `1.1.0` | https://example.com | 2026-01-01 | lead |
| `react` | `[VERIFY: from manifest/docs]` | — | — | — |

## Rules
"""


class Dependencies(unittest.TestCase):
    def test_reads_npm_and_pip_manifests(self):
        root = project(**{"package.json": PACKAGE_JSON,
                          "requirements.txt": "httpx==0.27.0  # client\n-r other.txt\nrich>=13\n",
                          "node_modules__x__package.json": json.dumps({"dependencies": {"ignored": "1.0.0"}})})
        self.addCleanup(shutil.rmtree, root)
        deps = {d["name"]: d for d in research.dependencies(root)}
        self.assertEqual(set(deps), {"left-pad", "react", "httpx", "rich"})
        self.assertEqual(deps["left-pad"]["exact"], "1.2.0")
        self.assertIsNone(deps["react"]["exact"])
        self.assertEqual(deps["httpx"]["exact"], "0.27.0")
        self.assertEqual(deps["httpx"]["ecosystem"], "pypi")


class Versions(unittest.TestCase):
    def test_offline_findings(self):
        root = project(**{"package.json": PACKAGE_JSON, "requirements.txt": "httpx==0.27.0\n",
                          "docs__versions.md": VERSIONS})
        self.addCleanup(shutil.rmtree, root)
        findings = research.version_findings(root, research.dependencies(root))
        text = "\n".join(findings)
        self.assertIn("`react` is still marked [VERIFY", text)
        self.assertIn("`left-pad` is 1.1.0 here but 1.2.0", text)
        self.assertIn("no row for `httpx`", text)

    def test_missing_versions_file(self):
        root = project(**{"package.json": PACKAGE_JSON})
        self.addCleanup(shutil.rmtree, root)
        findings = research.version_findings(root, research.dependencies(root))
        self.assertEqual(len(findings), 1)
        self.assertIn("missing", findings[0])


class Lookup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Registry)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.env = {"POLIER_NPM_REGISTRY": f"{base}/npm", "POLIER_PYPI_REGISTRY": f"{base}/pypi"}
        cls.saved = {k: os.environ.get(k) for k in cls.env}
        os.environ.update(cls.env)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        for key, value in cls.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_exact_range_and_unknown(self):
        ok = research.lookup({"name": "left-pad", "spec": "1.2.0", "exact": "1.2.0", "ecosystem": "npm"})
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["published"], "2017-01-01")
        rng = research.lookup({"name": "react", "spec": "^18.3.1", "exact": None, "ecosystem": "npm"})
        self.assertFalse(rng["ok"])
        self.assertIn("pin it", rng["error"])
        missing = research.lookup({"name": "httpx", "spec": "==9.9.9", "exact": "9.9.9", "ecosystem": "pypi"})
        self.assertIn("not found", missing["error"])
        gone = research.lookup({"name": "nope", "spec": "1.0.0", "exact": "1.0.0", "ecosystem": "npm"})
        self.assertIn("lookup failed", gone["error"])

    def test_write_records_only_confirmed_versions(self):
        root = project(**{"package.json": PACKAGE_JSON, "requirements.txt": "httpx==0.27.0\n",
                          "docs__versions.md": VERSIONS})
        self.addCleanup(shutil.rmtree, root)
        result = run_tool("research.py", "versions", "--root", str(root), "--lookup", "--write")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)  # react stays a range
        text = (root / "docs" / "versions.md").read_text()
        self.assertIn("| `left-pad` | `1.2.0` | https://www.npmjs.com/package/left-pad/v/1.2.0 |", text)
        self.assertIn("| `httpx` | `0.27.0` | https://pypi.org/project/httpx/0.27.0/ |", text)
        self.assertIn("`react` | `[VERIFY", text)
        self.assertLess(text.index("httpx"), text.index("## Rules"))
        self.assertIn("react: range", result.stdout)

    def test_write_creates_versions_file(self):
        root = project(**{"requirements.txt": "httpx==0.28.1\n"})
        self.addCleanup(shutil.rmtree, root)
        result = run_tool("research.py", "versions", "--root", str(root), "--lookup", "--write")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        text = (root / "docs" / "versions.md").read_text()
        self.assertIn("`httpx` | `0.28.1`", text)
        self.assertNotIn("<runtime>", text)

    def test_write_needs_lookup(self):
        root = project()
        self.addCleanup(shutil.rmtree, root)
        self.assertEqual(run_tool("research.py", "versions", "--root", str(root), "--write").returncode, 2)


class Notes(unittest.TestCase):
    def test_note_lifecycle(self):
        root = project()
        self.addCleanup(shutil.rmtree, root)
        made = run_tool("research.py", "note", "SQLite WAL mode", "--root", str(root),
                        "--question", "Does WAL work on network drives?", "--task", "M03",
                        "--source", "https://sqlite.org/wal.html")
        self.assertEqual(made.returncode, 0, made.stderr)
        path = root / "docs" / "research" / "sqlite-wal-mode.md"
        text = path.read_text()
        self.assertIn("**Question:** Does WAL work on network drives?", text)
        self.assertIn("**Asked by:** M03", text)
        self.assertIn("- https://sqlite.org/wal.html (checked ", text)

        check = run_tool("research.py", "check", "--root", str(root))
        self.assertEqual(check.returncode, 1)
        self.assertIn("no answer", check.stdout)

        path.write_text(text.replace("<3–10 lines: the finding and what the project does because of it>",
                                     "No. WAL needs shared memory on one host; keep the database local.")
                            .replace("<what it confirms>", "WAL limits"))
        check = run_tool("research.py", "check", "--root", str(root))
        self.assertEqual(check.returncode, 0, check.stdout)

        again = run_tool("research.py", "note", "SQLite WAL mode", "--root", str(root),
                         "--source", "https://sqlite.org/howtocorrupt.html")
        self.assertIn("updated", again.stdout)
        self.assertIn("howtocorrupt", path.read_text())

    def test_rejects_non_url_source(self):
        root = project()
        self.addCleanup(shutil.rmtree, root)
        result = run_tool("research.py", "note", "x", "--root", str(root), "--source", "file:///etc/passwd")
        self.assertEqual(result.returncode, 2)

    def test_examples_have_no_research_findings(self):
        package = Path(__file__).resolve().parents[1]
        for example in ("minimal-cli", "monorepo-mini"):
            self.assertEqual(research.note_findings(package / "examples" / example), [])


if __name__ == "__main__":
    unittest.main()
