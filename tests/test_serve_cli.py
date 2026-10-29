"""tools/serve.py: argument handling and a real HTTP round trip via the CLI."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
import urllib.request

from dash_helpers import PACKAGE, sample_project


class ServeCliTest(unittest.TestCase):
    def test_help(self) -> None:
        result = subprocess.run([sys.executable, str(PACKAGE / "tools" / "serve.py"), "--help"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("--port", result.stdout)

    def test_server_starts_and_answers(self) -> None:
        root = sample_project()
        process = subprocess.Popen(
            [sys.executable, "-u", str(PACKAGE / "tools" / "serve.py"), str(root),
             "--port", "0", "--quiet"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            url = None
            for _ in range(40):
                line = process.stdout.readline()
                if not line:
                    break
                if "http://" in line:
                    url = line.strip().split()[-1]
                    break
            self.assertIsNotNone(url, "serve.py did not print its URL")
            with urllib.request.urlopen(url.rstrip("/") + "/api/health", timeout=10) as response:
                health = json.loads(response.read().decode("utf-8"))
            self.assertTrue(health["ok"])
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
