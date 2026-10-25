"""tools/smoke.py (PL-11): post-deploy check, record and environment checklist."""
from __future__ import annotations

import http.server
import json
import os
import threading
import unittest
from pathlib import Path

from helpers import make_project, run_tool, task

import check  # noqa: E402


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802  (http.server API)
        body = b"<h1>ok</h1>"
        status = 200 if self.path in ("/", "/login") else 500
        if self.path == "/login":
            body = b"<h1>login page</h1>"
        if status != 200:
            body = b"<h1>Internal Server Error</h1>" + b"x" * 400
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        if self.headers.get("Authorization") == "Bearer secret-token":
            self.send_response(200)
            self.end_headers()

    def log_message(self, *args):  # keep the test output quiet
        pass


class Smoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def smoke(self, root: Path, *args: str, **env):
        old = {key: os.environ.get(key) for key in env}
        os.environ.update({k: v for k, v in env.items() if v is not None})
        try:
            return run_tool("smoke.py", *args, cwd=root)
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_all_paths_ok_exits_zero_and_records(self):
        root = make_project([task()])
        result = self.smoke(root, "--url", self.url, "--path", "/", "--path", "/login",
                            "--root", str(root))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SMOKE OK", result.stdout)
        record = [line for line in result.stdout.splitlines() if line.startswith("record: ")]
        self.assertEqual(len(record), 1, result.stdout)
        stored = json.loads((root / record[0].removeprefix("record: ")).read_text())
        self.assertEqual(stored["result"], "pass")
        self.assertEqual(stored["exit_code"], 0)
        self.assertTrue((Path(root) / "reviews/evidence" / stored["log"]).is_file())

    def test_500_exits_one_with_status_and_body_excerpt(self):
        root = make_project([task()])
        result = self.smoke(root, "--url", self.url, "--path", "/boom", "--root", str(root))
        self.assertEqual(result.returncode, 1)
        self.assertIn("500", result.stdout + result.stderr)
        self.assertIn("Internal Server Error", result.stdout + result.stderr)
        record = [line for line in result.stdout.splitlines() if line.startswith("record: ")]
        stored = json.loads((root / record[0].removeprefix("record: ")).read_text())
        self.assertEqual(stored["result"], "fail")

    def test_connection_error_is_infra(self):
        root = make_project([task()])
        result = self.smoke(root, "--url", "http://127.0.0.1:1", "--path", "/", "--root", str(root))
        self.assertEqual(result.returncode, 1)
        record = [line for line in result.stdout.splitlines() if line.startswith("record: ")]
        self.assertEqual(len(record), 1, result.stdout)
        stored = json.loads((root / record[0].removeprefix("record: ")).read_text())
        self.assertEqual(stored["result"], "infra")

    def test_header_value_comes_from_environment(self):
        root = make_project([task()])
        missing = self.smoke(root, "--url", self.url, "--path", "/", "--header",
                             "Authorization: env:SMOKE_TEST_TOKEN", "--root", str(root))
        self.assertEqual(missing.returncode, 2)
        self.assertIn("SMOKE_TEST_TOKEN", missing.stderr)
        wrong_form = self.smoke(root, "--url", self.url, "--path", "/", "--header",
                                "Authorization: Bearer abc", "--root", str(root))
        self.assertEqual(wrong_form.returncode, 2)
        ok = self.smoke(root, "--url", self.url, "--path", "/", "--header",
                        "Authorization: env:SMOKE_TEST_TOKEN", "--root", str(root),
                        SMOKE_TEST_TOKEN="Bearer secret-token")
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)

    def test_record_names_the_running_task(self):
        root = make_project([task("M07")])
        result = self.smoke(root, "--url", self.url, "--path", "/", "--root", str(root),
                            "--name", "deploy-smoke")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("M07-deploy-smoke", result.stdout)


class Environments(unittest.TestCase):
    def test_environment_without_smoke_url_warns(self):
        root = make_project([task()])
        (root / "docs").mkdir()
        (root / "docs/environments.md").write_text(
            "| Environment | Variables | Smoke URL |\n"
            "| --- | --- | --- |\n"
            "| preview | NEXT_PUBLIC_URL | https://preview.example.com/ |\n"
            "| production | NEXT_PUBLIC_URL | |\n",
            encoding="utf-8")
        warnings: list[str] = []
        check.check_environments(root, warnings)
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn("production", warnings[0])
        self.assertNotIn("preview", warnings[0])


if __name__ == "__main__":
    unittest.main()
