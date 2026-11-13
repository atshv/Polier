"""tools/change.py: new, show, link and apply on a copy of the minimal-cli fixture."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import PACKAGE, run_tool

FIXTURE = PACKAGE / "tests" / "fixtures" / "minimal-cli"

CONCEPT = """# Concept: bm

## Features

| Feature | Priority | Why |
| --- | --- | --- |
| add | MVP | core |

## User stories

- **US1** As Ana I want add so that I save links.
  - WHEN I add THEN it is saved.
"""

DELTAS = """### `docs/concept.md#features` — ADDED

| F2 | **Open** | MVP | quick access |

### `docs/concept.md#user-stories` — ADDED

- **US2** (F2) As Ana I want open so that I read a link.
  - WHEN I open THEN the browser starts.

### `docs/quality.md#definition-of-done-project` — ADDED

- **D7** `bm open` opens a stored link. (US2)
"""


def copy() -> Path:
    root = Path(tempfile.mkdtemp(prefix="pl-change-")) / "project"
    shutil.copytree(FIXTURE, root)
    (root / "docs" / "concept.md").write_text(CONCEPT)
    return root


def run(root, *args):
    return run_tool("change.py", *args, "--root", str(root))


def approve(root, note):
    out = run_tool("approve.py", "request", "--action", "scope_change", "--by", "lead",
                   "--note", note, "--root", str(root))
    ap = out.stdout.split()[1]
    return run_tool("approve.py", "grant", ap, "--root", str(root))


def add_task(root, status="done"):
    path = root / "board.json"
    board = json.loads(path.read_text())
    template = dict(next(t for t in board["tasks"] if t["id"] == "M01"))
    template.update(id="M07", title="Open", status=status, satisfies=["D7"],
                    depends_on=["M01"], stage=2, evidence=["pytest: 3 passed"])
    board["tasks"].append(template)
    path.write_text(json.dumps(board, indent=2) + "\n")
    run_tool("render_status.py", str(root))


def write_deltas(root, deltas=DELTAS):
    path = root / "changes" / "C01" / "proposal.md"
    text = path.read_text().replace("## Deltas to the living docs\n",
                                    "## Deltas to the living docs\n\n" + deltas)
    path.write_text(text)


class New(unittest.TestCase):
    def test_a1_creates_a_draft_and_prints_the_id(self):
        root = copy()
        result = run(root, "new", "Export")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("C01", result.stdout)
        text = (root / "changes" / "C01" / "proposal.md").read_text()
        self.assertTrue(text.startswith("# C01 — Export\n"))
        self.assertIn("**Status:** draft", text)
        second = run(root, "new", "More", "--json")
        self.assertEqual(json.loads(second.stdout)["id"], "C02")

    def test_no_project_is_a_usage_error(self):
        empty = Path(tempfile.mkdtemp(prefix="pl-change-empty-"))
        self.assertEqual(run(empty, "new", "Export").returncode, 2)
        self.assertFalse((empty / "changes").exists())


class Show(unittest.TestCase):
    def test_show_one_all_and_unknown(self):
        root = copy()
        self.assertIn("NO CHANGE PROPOSALS", run(root, "show").stdout)
        run(root, "new", "Export")
        one = json.loads(run(root, "show", "C01", "--json").stdout)
        self.assertEqual((one["status"], one["tasks"], one["approval"]), ("draft", [], None))
        self.assertIn("C01 · draft · Export", run(root, "show").stdout)
        self.assertEqual(run(root, "show", "C09").returncode, 1)


class Link(unittest.TestCase):
    def test_a6_an_unknown_task_is_refused(self):
        root = copy()
        run(root, "new", "Export")
        before = (root / "changes" / "C01" / "proposal.md").read_text()
        result = run(root, "link", "C01", "--task", "M99")
        self.assertEqual(result.returncode, 1)
        self.assertIn("M99", result.stderr)
        self.assertEqual((root / "changes" / "C01" / "proposal.md").read_text(), before)
        self.assertEqual(run(root, "link", "C01", "--task", "M01", "M02").returncode, 0)
        self.assertEqual(json.loads(run(root, "show", "C01", "--json").stdout)["tasks"], ["M01", "M02"])
        self.assertEqual(run(root, "link", "C05", "--task", "M01").returncode, 1)


class Apply(unittest.TestCase):
    def prepared(self, status="done"):
        root = copy()
        add_task(root, status)
        run(root, "new", "Open")
        write_deltas(root)
        run(root, "link", "C01", "--task", "M07")
        return root

    def test_a3_refuses_without_approval_or_with_an_open_task(self):
        root = self.prepared(status="review")
        before = (root / "docs" / "concept.md").read_text()
        result = run(root, "apply", "C01")
        self.assertEqual(result.returncode, 1)
        self.assertIn("scope_change approval", result.stderr)
        approve(root, "C01 open")
        result = run(root, "apply", "C01")
        self.assertEqual(result.returncode, 1)
        self.assertIn("M07", result.stderr)
        self.assertEqual((root / "docs" / "concept.md").read_text(), before)

    def test_a2_a_bad_delta_is_named_and_nothing_changes(self):
        root = self.prepared()
        approve(root, "C01 open")
        path = root / "changes" / "C01" / "proposal.md"
        path.write_text(path.read_text().replace("#user-stories", "#stories-of-nobody"))
        before = (root / "docs" / "concept.md").read_text()
        result = run(root, "apply", "C01")
        self.assertEqual(result.returncode, 1)
        self.assertIn("delta 2", result.stderr)
        self.assertEqual((root / "docs" / "concept.md").read_text(), before)
        self.assertIn("**Status:** draft", path.read_text())

    def test_a4_and_a5_apply_merges_and_the_fixture_still_passes_check(self):
        root = self.prepared()
        approve(root, "C01 open")
        result = run(root, "apply", "C01", "--by", "ana")
        self.assertEqual(result.returncode, 0, result.stderr)
        for target in ("docs/concept.md#features", "docs/concept.md#user-stories",
                       "docs/quality.md#definition-of-done-project"):
            self.assertIn(f"changed: {target}", result.stdout)
        concept = (root / "docs" / "concept.md").read_text()
        self.assertIn("| add | MVP | core |\n| F2 | **Open**", concept)
        self.assertIn("- **US2** (F2)", concept)
        quality = (root / "docs" / "quality.md").read_text()
        self.assertIn("- **D6** The README explains installation and the five core commands.\n- **D7**", quality)
        self.assertRegex((root / "changes" / "C01" / "proposal.md").read_text(),
                         r"\*\*Status:\*\* applied \d{4}-\d\d-\d\d by ana")
        checked = run_tool("check.py", str(root))
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertIn("passes the mandatory checks", checked.stdout)

    def test_a_second_apply_is_a_noop_with_exit_0(self):
        root = self.prepared()
        approve(root, "C01 open")
        run(root, "apply", "C01")
        concept = (root / "docs" / "concept.md").read_text()
        again = run(root, "apply", "C01")
        self.assertEqual(again.returncode, 0)
        self.assertIn("already applied", again.stdout)
        self.assertEqual((root / "docs" / "concept.md").read_text(), concept)

    def test_unknown_proposal_is_refused(self):
        self.assertEqual(run(copy(), "apply", "C03").returncode, 1)


if __name__ == "__main__":
    unittest.main()
