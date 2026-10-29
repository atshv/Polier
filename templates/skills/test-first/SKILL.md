---
name: Write tests first
description: Use when implementing behaviour that acceptance criteria describe; write the failing test before the code.
---

1. Read the acceptance criteria of the task (A1, A2, …) and pick the first one that is not covered by a test.
2. Write one test that fails for the right reason. Run it and keep the failure output.
3. Write the smallest code change that makes the test pass. Run the test again.
4. Refactor only while the tests stay green.
5. Repeat for the next criterion. Name each test after the criterion it proves.

Do not weaken, skip or delete an existing test to get green. If a test is wrong, say why in the handoff.
