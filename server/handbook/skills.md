# Skills

A skill is a short, reusable instruction with a description of *when* it applies — "Use when implementing behaviour that acceptance criteria describe". Agents read the description and follow the skill when it fits.

## The format

Skills use the Agent Skills layout, so interactive Claude Code in the project finds them on its own:

```text
.claude/skills/
  test-first/
    SKILL.md
```

```markdown
---
name: Write tests first
description: Use when implementing behaviour that acceptance criteria describe; write the failing test before the code.
---

1. Read the acceptance criteria of the task …
2. Write one test that fails for the right reason …
```

The `description` is the most important line: it decides when the skill is used. Start it with "Use when …".

## Start with the examples

**AI → Skills** lists five examples shipped with Polier — *Write tests first*, *Stay in scope*, *Review checklist*, *Prove it with gates*, *Write a handoff*. **Add to project** copies one into `.claude/skills/`; edit it there or in the dashboard to match your team.

## Write your own

**New skill** asks for a name, the ID (folder name), the description and the instructions in Markdown. Good skills are:

- **Narrow** — one habit per skill.
- **Checkable** — steps someone could verify in a review.
- **Short** — under a page; link to a doc for the details.

## How agents use skills

Headless sessions inline the skills of their [agent](polier:agents) into the prompt, so they work with any provider. Interactive Claude Code sessions discover every skill in `.claude/skills/` and load one when its description matches the work.

> [!NOTE]
> Skills are project files. Commit them, review changes to them like code, and keep them in sync with `ARCHITECTURE.md` and `AGENTS.md`.
