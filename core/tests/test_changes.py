"""core.changes: parsing, validation and merging of change proposals."""
from __future__ import annotations

import unittest
from pathlib import Path

from core import approvals, changes
from core.errors import PolierError

from .fixtures import project, task

CONCEPT = """# Concept

## Features

| Feature | Priority | Why |
| --- | --- | --- |
| scan | MVP | core |

The MVP is small.

## User stories

- **US1** As Ana I want a scan so that it is fast.
  - WHEN I scan THEN it works.

Every MVP feature has a story.

## Risks

Old risk text.
Second line.
"""


def proposal(deltas: str, tasks=("M01",), status="draft", title="Export") -> str:
    linked = "\n".join(f"- {t}" for t in tasks) or "none yet"
    return (f"# C01 — {title}\n\n**Status:** {status} · **Asked by:** owner, 2026-11-13\n\n"
            f"<!-- a comment with ### `x#y` — ADDED inside -->\n\n## Why\n\nBecause.\n\n"
            f"## Linked tasks\n\n{linked}\n\n## Deltas to the living docs\n\n{deltas}\n"
            f"## Approval\n\nscope_change for C01.\n")


ADDED = """### `docs/concept.md#features` — ADDED

| F2 | **Export** | MVP | backup |

### `docs/concept.md#user-stories` — ADDED

- **US2** As Ana I want export so that I keep my data.
  - WHEN I export THEN a file appears.
"""

MODIFIED = """### `docs/concept.md#risks` — MODIFIED

**Old:**
```
Old risk text.
```

**New:**
```
New risk text.
```
"""


def setup(text: str, status="done"):
    root = project([task("M01", status=status)], repo=False)
    (root / "docs").mkdir()
    (root / "docs" / "concept.md").write_text(CONCEPT)
    path = changes.proposal_path(root, "C01")
    path.parent.mkdir(parents=True)
    path.write_text(text)
    return root


def grant(root, note="C01 export"):
    record = approvals.request(root, "scope_change", by="lead", note=note)
    approvals.grant(root, record["id"], "owner")


def concept(root) -> str:
    return (root / "docs" / "concept.md").read_text()


class Parse(unittest.TestCase):
    def test_reads_status_tasks_and_deltas_and_skips_comments(self):
        parsed = changes.parse(proposal(ADDED + "\n" + MODIFIED, tasks=("M01", "M02")))
        self.assertEqual(parsed["errors"], [])
        self.assertEqual((parsed["id"], parsed["status"], parsed["tasks"]), ("C01", "draft", ["M01", "M02"]))
        self.assertEqual([d["kind"] for d in parsed["deltas"]], ["ADDED", "ADDED", "MODIFIED"])
        self.assertEqual(parsed["deltas"][2]["old"], "Old risk text.")
        self.assertEqual(parsed["deltas"][2]["new"], "New risk text.")

    def test_the_template_parses_without_problems_and_without_deltas(self):
        text = changes.TEMPLATE.read_text().replace("{{ID}}", "C01").replace(
            "{{TITLE}}", "T").replace("{{BY}}", "o").replace("{{DATE}}", "2026-01-01")
        parsed = changes.parse(text)
        self.assertEqual(parsed["errors"], [])
        self.assertEqual((parsed["status"], parsed["deltas"], parsed["tasks"]), ("draft", [], []))

    def test_problems_are_named(self):
        bad = proposal("### `docs/concept.md#risks` — MODIFIED\n\nno blocks\n")
        self.assertTrue(any("delta 1" in e and "Old" in e for e in changes.parse(bad)["errors"]))
        bad = proposal("### docs/concept.md — ADDED\n\ntext\n")
        self.assertTrue(any("delta 1" in e for e in changes.parse(bad)["errors"]))
        self.assertTrue(changes.parse("no title\n")["errors"])
        self.assertTrue(any("unknown status" in e for e in changes.parse(proposal("", status="weird"))["errors"]))

    def test_valid_id(self):
        self.assertTrue(changes.valid_id("C01"))
        self.assertFalse(changes.valid_id("C1"))
        self.assertFalse(changes.valid_id("../C01"))


class Merge(unittest.TestCase):
    def test_added_extends_the_table_and_the_list_in_place(self):
        root = setup(proposal(ADDED))
        grant(root)
        result = changes.apply(root, "C01", "lead")
        self.assertTrue(result["applied"])
        self.assertEqual(result["changed"], ["docs/concept.md#features", "docs/concept.md#user-stories"])
        text = concept(root)
        self.assertIn("| scan | MVP | core |\n| F2 | **Export** | MVP | backup |\n\nThe MVP is small.", text)
        self.assertIn("  - WHEN I scan THEN it works.\n- **US2** As Ana", text)
        self.assertIn("a file appears.\n\nEvery MVP feature", text)

    def test_modified_and_removed(self):
        removed = ("### `docs/concept.md#risks` — REMOVED\n\n**Old:**\n```\nSecond line.\n```\n")
        root = setup(proposal(MODIFIED + "\n" + removed))
        grant(root)
        changes.apply(root, "C01", "lead")
        self.assertTrue(concept(root).endswith("## Risks\n\nNew risk text.\n"))

    def test_a_second_modified_matches_the_text_after_the_first(self):
        second = ("### `docs/concept.md#risks` — MODIFIED\n\n**Old:**\n```\nNew risk text.\n```\n\n"
                  "**New:**\n```\nNewest.\n```\n")
        root = setup(proposal(MODIFIED + "\n" + second))
        grant(root)
        changes.apply(root, "C01", "lead")
        self.assertIn("Newest.\nSecond line.", concept(root))

    def test_a_missing_heading_or_old_text_refuses_and_changes_nothing(self):
        for delta, needle in (
            ("### `docs/concept.md#nowhere` — ADDED\n\ntext\n", "not found"),
            ("### `docs/missing.md#x` — ADDED\n\ntext\n", "cannot read"),
            (MODIFIED.replace("Old risk text.", "Not there."), "old text not found"),
        ):
            root = setup(proposal(ADDED + "\n" + delta))
            grant(root)
            before = concept(root)
            with self.assertRaises(PolierError) as caught:
                changes.apply(root, "C01", "lead")
            self.assertIn("delta 3", str(caught.exception))
            self.assertIn(needle, str(caught.exception))
            self.assertEqual(concept(root), before)
            self.assertEqual(changes.load(root, "C01")["status"], "draft")

    def test_a_heading_that_appears_twice_is_ambiguous(self):
        root = setup(proposal(ADDED))
        (root / "docs" / "concept.md").write_text(CONCEPT + "\n## Features\n\nagain\n")
        grant(root)
        with self.assertRaises(PolierError) as caught:
            changes.apply(root, "C01", "lead")
        self.assertIn("ambiguous", str(caught.exception))

    def test_a_file_outside_the_project_is_refused(self):
        root = setup(proposal("### `../outside.md#x` — ADDED\n\ntext\n"))
        grant(root)
        with self.assertRaises(PolierError) as caught:
            changes.apply(root, "C01", "lead")
        self.assertIn("outside", str(caught.exception))


class Gates(unittest.TestCase):
    def test_no_approval_naming_the_id_refuses(self):
        root = setup(proposal(ADDED))
        before = concept(root)
        with self.assertRaises(PolierError) as caught:
            changes.apply(root, "C01", "lead")
        self.assertIn("scope_change approval", str(caught.exception))
        grant(root, note="C010 something else")
        with self.assertRaises(PolierError):
            changes.apply(root, "C01", "lead")
        pending = approvals.request(root, "scope_change", by="lead", note="C01 pending only")
        self.assertEqual(pending["status"], "pending")
        with self.assertRaises(PolierError):
            changes.apply(root, "C01", "lead")
        self.assertEqual(concept(root), before)

    def test_only_the_first_word_of_the_requested_note_names_the_proposal(self):
        root = setup(proposal(ADDED))
        record = approvals.request(root, "scope_change", by="lead", note="C02 export")
        approvals.grant(root, record["id"], "owner", "fine, but keep C01 separate")
        self.assertIsNone(changes.find_approval(root, "C01"))
        with self.assertRaises(PolierError):
            changes.apply(root, "C01", "lead")
        record = approvals.request(root, "scope_change", by="lead", note="keep C01 apart")
        approvals.grant(root, record["id"], "owner")
        self.assertIsNone(changes.find_approval(root, "C01"))
        grant(root, note="C01 export")
        self.assertIsNotNone(changes.find_approval(root, "C01"))

    def test_a_task_that_is_not_done_refuses(self):
        root = setup(proposal(ADDED), status="review")
        grant(root)
        before = concept(root)
        with self.assertRaises(PolierError) as caught:
            changes.apply(root, "C01", "lead")
        self.assertIn("M01", str(caught.exception))
        self.assertEqual(concept(root), before)

    def test_apply_sets_status_and_a_second_run_does_nothing(self):
        root = setup(proposal(ADDED))
        grant(root)
        changes.apply(root, "C01", "lead")
        parsed = changes.load(root, "C01")
        self.assertEqual(parsed["status"], "applied")
        self.assertRegex(changes.proposal_path(root, "C01").read_text(),
                         r"\*\*Status:\*\* applied \d{4}-\d\d-\d\d by lead · \*\*Asked by:\*\*")
        after = concept(root)
        again = changes.apply(root, "C01", "lead")
        self.assertFalse(again["applied"])
        self.assertIn("already applied", again["note"])
        self.assertEqual(concept(root), after)

    def test_a_proposal_without_deltas_applies(self):
        root = setup(proposal(""))
        grant(root)
        self.assertEqual(changes.apply(root, "C01", "lead")["changed"], [])
        self.assertEqual(changes.load(root, "C01")["status"], "applied")


class NewAndLink(unittest.TestCase):
    def test_create_numbers_proposals_and_fills_the_template(self):
        root = project([task("M01")], repo=False)
        self.assertEqual(changes.create(root, "Export  data", "ana"), "C01")
        self.assertEqual(changes.create(root, "Second"), "C02")
        parsed = changes.load(root, "C01")
        self.assertEqual((parsed["title"], parsed["status"], parsed["errors"]), ("Export data", "draft", []))
        self.assertIn("ana", changes.proposal_path(root, "C01").read_text())
        self.assertEqual(changes.ids(root), ["C01", "C02"])

    def test_create_needs_a_title_and_a_board(self):
        with self.assertRaises(PolierError):
            changes.create(project([task("M01")], repo=False), "  ")
        empty = Path(project([task("M01")], repo=False)) / "sub"
        empty.mkdir()
        with self.assertRaises(PolierError):
            changes.create(empty, "x")

    def test_link_adds_known_tasks_once_and_refuses_unknown_ones(self):
        root = project([task("M01"), task("M02")], repo=False)
        changes.create(root, "Export")
        self.assertEqual(changes.link(root, "C01", ["M01"]), ["M01"])
        self.assertEqual(changes.link(root, "C01", ["M02", "M01"]), ["M01", "M02"])
        path = changes.proposal_path(root, "C01")
        before = path.read_text()
        with self.assertRaises(PolierError) as caught:
            changes.link(root, "C01", ["M99"])
        self.assertIn("M99", str(caught.exception))
        self.assertEqual(path.read_text(), before)
        self.assertEqual(changes.parse(before)["tasks"], ["M01", "M02"])
        self.assertTrue(before.endswith("\n"))
        with self.assertRaises(PolierError):
            changes.link(root, "C07", ["M01"])


class Visible(unittest.TestCase):
    """No delta may vanish silently."""

    SECTION = """### `docs/concept.md#risks` — ADDED

```markdown
## Export

New section text.
```
"""
    LATER = "### `docs/concept.md#features` — ADDED\n\n| F2 | x | MVP | y |\n"

    def test_a_fenced_heading_is_inserted_without_the_fence_and_later_deltas_apply(self):
        root = setup(proposal(self.SECTION + "\n" + self.LATER))
        grant(root)
        result = changes.apply(root, "C01", "lead")
        self.assertEqual(result["changed"], ["docs/concept.md#risks", "docs/concept.md#features"])
        text = concept(root)
        self.assertTrue(text.endswith("Second line.\n\n## Export\n\nNew section text.\n"))
        self.assertNotIn("```", text)
        self.assertIn("| F2 | x | MVP | y |", text)

    def test_an_unfenced_heading_in_a_body_is_an_error_and_nothing_is_written(self):
        unfenced = "### `docs/concept.md#risks` — ADDED\n\n#### Deeper\n\ntext\n"
        root = setup(proposal(unfenced))
        grant(root)
        before = concept(root)
        parsed = changes.parse(changes.proposal_path(root, "C01").read_text())
        self.assertTrue(any("outside a fenced block" in e for e in parsed["errors"]))
        with self.assertRaises(PolierError):
            changes.apply(root, "C01", "lead")
        self.assertEqual(concept(root), before)
        self.assertEqual(changes.load(root, "C01")["status"], "draft")

    def test_an_unfenced_section_heading_that_hides_a_later_delta_is_refused(self):
        hidden = ("### `docs/concept.md#risks` — ADDED\n\ntext\n\n## Export\n\nmore\n\n"
                  "### `docs/concept.md#features` — REMOVED\n\n**Old:**\n```\n| scan | MVP | core |\n```\n")
        root = setup(proposal(hidden))
        grant(root)
        before = concept(root)
        errors = changes.parse(changes.proposal_path(root, "C01").read_text())["errors"]
        self.assertTrue(any("outside the deltas section" in e and "features" in e for e in errors), errors)
        with self.assertRaises(PolierError) as caught:
            changes.apply(root, "C01", "lead")
        self.assertIn("not valid", str(caught.exception))
        self.assertEqual(concept(root), before)

    def test_a_delta_after_the_section_is_an_error(self):
        late = proposal(ADDED) + "\n" + MODIFIED
        errors = changes.parse(late)["errors"]
        self.assertTrue(any("outside the deltas section" in e for e in errors), errors)


class Targets(unittest.TestCase):
    def refused(self, target: str, make=None, policy_json=None):
        delta = f"### `{target}#why` — ADDED\n\ntext\n"
        root = setup(proposal(delta))
        if make:
            make(root)
        if policy_json:
            (root / "policy.json").write_text(policy_json)
        grant(root)
        with self.assertRaises(PolierError) as caught:
            changes.apply(root, "C01", "lead")
        self.assertIn("delta 1", str(caught.exception))
        self.assertEqual(changes.load(root, "C01")["status"], "draft")
        return str(caught.exception)

    @staticmethod
    def doc(path):
        def make(root):
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text("# T\n\n## Why\n\nx\n")
        return make

    def test_the_proposal_itself_and_other_proposals(self):
        self.refused("changes/C01/proposal.md")
        self.refused("changes/C02/proposal.md", self.doc("changes/C02/proposal.md"))

    def test_records_folders(self):
        for path in ("reviews/M01.md", "tasks/M01.md", "runs/notes.md"):
            self.refused(path, self.doc(path))

    def test_board_factory_and_policy_files(self):
        for name in ("board.json", "factory.json", "policy.json"):
            self.refused(name, self.doc(name))

    def test_protected_paths_from_the_policy(self):
        self.refused("secrets/notes.md", self.doc("secrets/notes.md"),
                     policy_json='{"enabled": true}')
        self.refused("CHANGELOG.md", self.doc("CHANGELOG.md"),
                     policy_json='{"enabled": true, "scope": {"protected_paths": ["CHANGELOG.md"]}}')


if __name__ == "__main__":
    unittest.main()
