# Research: what 2026 reports say about verifying agent work

**Question:** Where do agent-built projects fail today, and what does that mean for Polier's direction?
**Asked by:** concept (CON-10)
**Date:** 2026-11-12

## Answer

- Reviewing AI-generated code is the top bottleneck for developers and leaders alike; only 45 % have traceability from agent activity to the code it produced, only 35 % say agents always follow the organisation's standards (Qodo survey, vendor source).
- Writing code speeds up faster than the stages needed to ship it; long-running agents struggle to verify themselves and sometimes try to game their verifiers; agent activity drops from commits to releases (arXiv 2609.04681, preprint).
- Agents changed tests in only about half of the pull requests where tests were relevant (analysis of 4,882 agent PRs, secondary source).

For Polier: its edge is traceability (board → runs → evidence → review) and owner gates. The weak link is that this evidence is cooperative and that nothing measures whether agents follow the process. Direction: make evidence re-checkable and measure process adherence, rather than add more planning documents.

## Sources

- https://www.qodo.ai/blog/state-of-ai-code-quality-report-2026/ (checked 2026-11-12) — survey figures on review bottleneck and traceability
- https://arxiv.org/pdf/2609.04681 (checked 2026-11-12) — verification and cost economics in the agentic lifecycle
- https://arxiv.org/pdf/2609.24234 (checked 2026-11-12) — framework for supervising coding agents
- https://dev.to/jenueldev/the-state-of-ai-in-software-development-in-2026-agents-productivity-and-the-verification-4jf8 (checked 2026-11-12) — agent PR test-change rate

## Open

- The figures come from a vendor survey and preprints; read the papers in full before quoting numbers in Polier's README. [VERIFY]
