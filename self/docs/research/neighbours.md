# Research: what neighbouring frameworks do that Polier does not

**Question:** Which ideas of comparable agent-workflow frameworks would close a real gap in Polier?
**Asked by:** concept (CON-05)
**Date:** 2026-11-12

## Answer

| Framework | Core idea | Polier today | Take over? |
| --- | --- | --- | --- |
| GitHub Spec Kit | constitution → specify → clarify → plan → tasks → analyze → implement; `analyze` checks spec, plan and tasks against each other and the constitution | interview, concept, board; `check.py` traceability | partly: an explicit ambiguity pass before the plan closes |
| OpenSpec | each change is a folder with proposal, tasks and spec deltas (ADDED/MODIFIED/REMOVED), archived into living specs | new features = "a new stage"; no delta artifact | **yes**: change proposals for a shipped product |
| Kiro | specs per feature (requirements in EARS, design, tasks), steering files, event hooks | WHEN–THEN acceptance (EARS-like), AGENTS.md, guard hooks | no new idea |
| BMAD Method | role agents, scale-adaptive tracks (Quick Flow … Enterprise) | roles, profiles S/M/L; every change goes through the full line | **yes**: a quick track |
| Superpowers (Claude Code) | brainstorming, enforced TDD, a fresh subagent per task with a two-stage review (spec compliance, then code quality) | fresh subagents, one review with a rubric | maybe: two review lenses as default at M |
| Task Master | PRD → tasks, complexity analysis, expansion of complex tasks | `complexity` on the board, briefs | no |

No neighbour covers release, stores, legal texts and operation the way the catalog does, and none records gate evidence with owner approvals. The verification reports below make that the place to deepen, not spec writing.

## Sources

- https://developer.microsoft.com/blog/spec-driven-development-spec-kit/ (checked 2026-11-12) — Spec Kit workflow and constitution
- https://codemyspec.com/blog/github-spec-kit-guide (checked 2026-11-12) — clarify and analyze steps
- https://developertoolkit.ai/en/ecosystem/frameworks/openspec/ (checked 2026-11-12) — change folders, deltas, archive into living specs
- https://redreamality.com/garden/notes/openspec-guide (checked 2026-11-12) — ADDED/MODIFIED/REMOVED deltas
- https://sdtimes.com/ai/amazon-launches-spec-driven-ai-ide-kiro/ (checked 2026-11-12) — Kiro specs, steering, hooks
- https://redreamality.com/garden/notes/bmad-method-guide/ (checked 2026-11-12) — BMAD roles and scale-adaptive tracks
- https://blog.marcnuri.com/superpowers-claude-code-skills-framework (checked 2026-11-12) — Superpowers skills and two-stage review
- https://regis-rcr.github.io/claude-framework-research/frameworks/claude-task-master.html (checked 2026-11-12) — Task Master PRD parsing and complexity

## Open

- Most sources are third-party guides; command names change between versions. Check the primary repositories (github/spec-kit, Fission-AI/OpenSpec, bmad-code-org/BMAD-METHOD, obra/superpowers) before copying any format. [VERIFY]
