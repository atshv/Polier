# Project Input: Polier next

> Station 1 (idea). Polier run on itself: the product is Polier, the factory is Polier. The block is what the generator reads.

```text
PROJECT:        Polier keeps AI agents to a plan with evidence, owner approvals and a write guard, from idea to an operated product. It cannot yet tell whether agents actually follow its process, it learns nothing from the projects it runs, and it is heavy for small changes after the first release. Polier next makes Polier measure itself (evals), learn from its own project records (retro), evolve a shipped product through change proposals and a quick track, and make its evidence harder to fake. Out of scope: a hosted service, a UI beyond status pages, writing product code itself.
PLATFORMS:      cli
TRAITS:         ai, brownfield, public
MODE:           brownfield
PROFILE:        S
LANGUAGE:       English (docs, code, prompts); README also in German
BUDGET:         no money; agent tokens as usual; no deadline
EXISTING REPO:  .. (the Polier repository, this folder's parent)
```

## Problem

- Nobody measures whether an agent with Polier behaves better than without it: the 621 tests check the tools, not the agent's process (does it call `pl_factory advance` instead of editing `factory.json`, does it stop at an out-of-scope write?).
- Every project leaves `runs/`, `reviews/` and `reviews/approvals/` behind, but the failure classes in them (repeated gate failures, review rounds, guard denials) never flow back into the catalog, templates or prompts. `prompt/generator.md` says to change the generator "only for a named class of errors", yet nothing names them.
- After the operate station a product changes through "a new stage". There is no artifact that states what changes in the concept and the acceptance, and no light path for a bug fix or a small feature.
- Gate records and approvals are cooperative evidence (`docs/guard-limits.md`). Studies of 2026 name verification as the bottleneck of agent work and report agents that game their verifiers.

## Users

- The **owner**, who builds a product with Polier in DSH or Claude Code and answers its dialogs.
- The **Polier maintainer**, who decides what changes in Polier.
- The **agents** (lead, builders, reviewers) that run inside Polier.

## Success signal

Four weeks after the first release of Polier next: the eval suite runs in CI and shows a measurable lead of Polier over the no-plugin baseline on the process scenarios; one change to Polier was made because the retro named its error class; one shipped fixture project got a feature through a change proposal and a fix through the quick track.

## Non-goals

- No hosted service, account or telemetry: records stay in the projects; the retro reads only folders the owner names.
- No own spec format competing with Spec Kit or OpenSpec; Polier keeps its catalog, concept and board.
- No autonomous self-modification: the retro proposes, the maintainer decides through the normal line and approvals.

## Platforms

`cli`: Polier is Python tools plus two harness plugins. Claude Code ships first for evals (`claude plugin eval` exists); DSH follows where its harness allows.

## Budget and time

No money. Token cost of eval runs is the main running cost; the suite stays small (≤ 20 cases) and runs on demand and before releases, not on every push.
