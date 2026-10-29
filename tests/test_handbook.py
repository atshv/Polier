"""The handbook shipped with the dashboard: index, pages, links and the API route."""
from __future__ import annotations

import json
import re
import unittest
import urllib.request
from pathlib import Path

from dash_helpers import PACKAGE, sample_project

from core import handbook
from server.app import DashboardApp, DashboardServer

FOLDER = PACKAGE / "server" / "handbook"


class HandbookTest(unittest.TestCase):
    def setUp(self) -> None:
        self.book = handbook.load(PACKAGE)
        self.pages = [page for space in self.book["spaces"]
                      for section in space["sections"] for page in section["pages"]]

    def test_every_listed_page_exists_once_and_has_a_title_and_summary(self) -> None:
        ids = [page["id"] for page in self.pages]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(self.book["pages"], len(ids))
        for page in self.pages:
            self.assertTrue(page["text"].startswith("# "), page["id"])
            self.assertTrue(page["summary"], page["id"])

    def test_no_markdown_file_is_left_out_of_the_index(self) -> None:
        listed = {page["id"] for page in self.pages}
        on_disk = {path.stem for path in FOLDER.glob("*.md")}
        self.assertEqual(on_disk - listed, set())

    def test_internal_links_point_to_existing_pages(self) -> None:
        listed = {page["id"] for page in self.pages}
        for page in self.pages:
            for target in re.findall(r"\]\(polier:([a-z0-9-]+)\)", page["text"]):
                self.assertIn(target, listed, f"{page['id']} links to unknown page {target}")

    def test_code_fences_are_closed(self) -> None:
        for page in self.pages:
            fences = [line for line in page["text"].splitlines() if line.lstrip().startswith("```")]
            self.assertEqual(len(fences) % 2, 0, page["id"])

    def test_the_api_reference_names_every_api_route(self) -> None:
        source = (PACKAGE / "server" / "app.py").read_text(encoding="utf-8")
        routes = set(re.findall(r'path == "(/api/[a-z/-]+)"', source))
        reference = "\n".join(page["text"] for page in self.pages if page["id"].startswith("api-"))
        missing = sorted(route for route in routes if route not in reference)
        self.assertEqual(missing, [])

    def test_a_broken_index_is_reported(self) -> None:
        root = Path(sample_project())
        (root / "server" / "handbook").mkdir(parents=True)
        (root / "server" / "handbook" / "index.json").write_text("{", encoding="utf-8")
        with self.assertRaises(Exception):
            handbook.load(root)


class HandbookRouteTest(unittest.TestCase):
    def test_get_handbook(self) -> None:
        app = DashboardApp(sample_project(), host="127.0.0.1", port=0, quiet=True)
        server = DashboardServer(app, port=0).start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{app.port}/api/handbook", timeout=30) as response:
                value = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
        self.assertEqual([space["id"] for space in value["spaces"]], ["guides", "api"])
        self.assertGreater(value["pages"], 20)


if __name__ == "__main__":
    unittest.main()
