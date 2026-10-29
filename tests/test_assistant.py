"""core/assistant.py: context prompt, answer parsing and conversation store."""
from __future__ import annotations

import unittest

from dash_helpers import sample_project

from core import assistant


class AssistantCoreTest(unittest.TestCase):
    def test_conversation_store(self) -> None:
        root = sample_project()
        conversation = assistant.create(root)
        self.assertTrue(conversation["id"].startswith("conv-"))
        updated = assistant.append_message(root, conversation["id"],
                                           {"role": "user", "content": "What is blocked?"})
        self.assertEqual(updated["messages"][0]["content"], "What is blocked?")
        self.assertEqual(updated["title"], "What is blocked?")
        self.assertEqual(len(assistant.list_conversations(root)), 1)
        loaded = assistant.load(root, conversation["id"])
        self.assertEqual(loaded["messages"][0]["role"], "user")
        assistant.delete(root, conversation["id"])
        self.assertEqual(assistant.list_conversations(root), [])

    def test_prompt_contains_context_and_question(self) -> None:
        root = sample_project()
        conversation = assistant.create(root)
        prompt = assistant.build_prompt(root, conversation, "Welche Gates fehlen?")
        self.assertIn("Polier project assistant", prompt)
        self.assertIn("canvas-mini", prompt)
        self.assertIn("Welche Gates fehlen?", prompt)
        self.assertIn("proposals", prompt)
        self.assertIn("F-01", prompt)

    def test_parse_answer_with_proposals(self) -> None:
        text = """Stage 7 is blocked by P6-16.

```json
{"proposals": [{"kind": "state", "title": "Block ENG-01", "reason": "needs the spike",
                "payload": {"task": "ENG-01", "status": "blocked", "note": "x"}},
               {"kind": "bogus", "title": "ignored"}]}
```"""
        parsed = assistant.parse_answer(text)
        self.assertIn("Stage 7 is blocked", parsed["answer"])
        self.assertEqual(len(parsed["proposals"]), 1)
        self.assertEqual(parsed["proposals"][0]["kind"], "state")
        self.assertEqual(parsed["proposals"][0]["payload"]["task"], "ENG-01")
        plain = assistant.parse_answer("Just an answer without proposals.")
        self.assertEqual(plain["answer"], "Just an answer without proposals.")
        self.assertEqual(plain["proposals"], [])


if __name__ == "__main__":
    unittest.main()
