"""core/plans.py: the interview draft and the generator prompt (2.0)."""
from __future__ import annotations

import unittest

from dash_helpers import PACKAGE, empty_project, sample_project

from core import plans
from core.errors import PolierError

ANSWERS = {
    "mode": "greenfield",
    "name": "Notes",
    "goal": "A calm note-taking app for teams.",
    "platform": "desktop web",
    "stack": "TypeScript, Vite",
    "questions": [{"question": "Hosting?", "answer": "Switzerland"}],
}


class PlansTest(unittest.TestCase):
    def test_draft_roundtrip_and_validation(self) -> None:
        root = empty_project()
        draft = plans.save_answers(root, ANSWERS)
        self.assertEqual(draft["status"], "draft")
        self.assertEqual(draft["answers"]["name"], "Notes")
        loaded = plans.load(root)
        self.assertEqual(loaded["answers"]["goal"], ANSWERS["goal"])
        with self.assertRaises(PolierError):
            plans.save_answers(empty_project(), {"mode": "greenfield", "name": "x"})

    def test_generator_prompt_contains_the_answers(self) -> None:
        root = empty_project()
        plans.save_answers(root, ANSWERS)
        prompt = plans.generator_prompt(root, PACKAGE)
        self.assertIn("A calm note-taking app for teams.", prompt)
        self.assertIn("Dashboard run instructions", prompt)
        self.assertIn("Hosting?", prompt)
        info = plans.record_prompt(root, PACKAGE)
        self.assertTrue(info["path"].endswith(".md"))
        self.assertTrue(open(info["path"], encoding="utf-8").read().startswith("#"))

    def test_approve_needs_a_valid_board(self) -> None:
        empty = empty_project()
        plans.save_answers(empty, ANSWERS)
        with self.assertRaises(PolierError):
            plans.approve(empty, PACKAGE)

        project = sample_project()
        plans.save_answers(project, ANSWERS)
        result = plans.approve(project, PACKAGE)
        self.assertEqual(result["status"], "approved")
        self.assertEqual(plans.status(project)["status"], "approved")


if __name__ == "__main__":
    unittest.main()
