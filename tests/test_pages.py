"""core/pages.py: the Markdown knowledge layer."""
from __future__ import annotations

import unittest

from dash_helpers import sample_project

from core import pages


class PagesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_project()

    def test_index_has_collections_and_pages(self) -> None:
        value = pages.index(self.root)
        self.assertGreater(value["counts"]["pages"], 5)
        ids = [collection["id"] for collection in value["collections"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("docs", ids)
        self.assertIn("tasks", ids)
        self.assertIn("reviews", ids)
        for page in value["pages"]:
            self.assertTrue(page["path"].endswith(".md"))
            self.assertIn("title", page)

    def test_page_content_links_backlinks_history(self) -> None:
        detail = pages.page(self.root, "docs/contracts.md") if (self.root / "docs/contracts.md").is_file() \
            else None
        path = "docs/contracts.md" if detail else pages.index(self.root)["pages"][0]["path"]
        detail = pages.page(self.root, path)
        self.assertTrue(detail["text"])
        self.assertIn("links", detail)
        self.assertIn("backlinks", detail)
        self.assertIn("history", detail)
        self.assertGreaterEqual(len(detail["history"]), 1)
        commit = detail["history"][0]["hash"]
        old = pages.page(self.root, path, commit)
        self.assertEqual(old["ref"], commit)

    def test_search(self) -> None:
        result = pages.search(self.root, "contract")
        self.assertTrue(result)
        self.assertTrue(all("score" in page for page in result))
        self.assertTrue(all("snippet" in page for page in result))
        self.assertEqual(pages.search(self.root, "x"), [])

    def test_traversal_is_refused(self) -> None:
        for bad in ("../board.json", "/etc/passwd", "node_modules/x.md", ""):
            with self.assertRaises(KeyError):
                pages.page(self.root, bad)

    def test_favorites_are_local(self) -> None:
        path = pages.index(self.root)["pages"][0]["path"]
        pages.set_favorites(self.root, [path, "../board.json"])
        self.assertEqual(pages.load_favorites(self.root)["favorites"], [path])
        pages.set_favorites(self.root, [])
        self.assertEqual(pages.load_favorites(self.root)["favorites"], [])


if __name__ == "__main__":
    unittest.main()
