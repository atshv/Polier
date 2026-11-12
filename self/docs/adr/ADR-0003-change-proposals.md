# ADR-0003: Change proposals as approved deltas to the living docs

**Date:** 2026-11-12 · **Status:** proposed · **Supersedes:** –

## Context

After the operate station a shipped product changes through "a new stage" (`prompt/generator.md`), but nothing records what changes in concept, acceptance and architecture (US3, D3). OpenSpec keeps each change as a folder with a proposal, tasks and ADDED/MODIFIED/REMOVED spec deltas that are merged into living specs when done (`docs/research/neighbours.md`). Polier already has the approval action `scope_change` (`core/policy.py`) and `factory.py scope` for platform and trait changes.

## Decision

A change is `changes/C<NN>/proposal.md` (from `templates/change-proposal.md`) with why, what, linked board tasks and one delta block per target `file#heading` (ADDED, MODIFIED with the old and the new text, REMOVED); it needs a granted `scope_change` approval before its tasks start, and `tools/change.py apply` merges the deltas only when every linked task is done, then marks the proposal `applied`.

## Consequences

- **Positive:** the living docs stay true after release; reviewers see the intent next to the diff; reuses approvals, board and state machine.
- **Negative:** one more file per change; a MODIFIED delta fails when the target text moved, which forces a fresh proposal edit.
- **Binds:** `core/changes.py`, `tools/change.py`, `templates/change-proposal.md`, `pl_change` in `plugin/lib/tools.mjs`, `tools/check.py` (a proposal with done tasks but not applied is a finding).
- **Prevents:** concept and acceptance drifting from what was approved and built.
- A change that adds a platform or trait runs `factory.py scope` in the same proposal; new catalog items then appear as usual.

## Alternatives

- **Edit the living docs directly in the task** — rejected: no record of what the owner approved.
- **Adopt OpenSpec's files as they are** — rejected: a second spec format next to concept and board (non-goal).
