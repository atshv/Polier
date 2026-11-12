# ADR-0004: The quick track is an ordinary task with a narrow entry

**Date:** 2026-11-12 · **Status:** proposed · **Supersedes:** –

## Context

A two-line fix should not reopen stations (US4, D4). BMAD offers scale-adaptive tracks (`docs/research/neighbours.md`). Polier's strength is that every path to `done` has gates, review and a handoff; a lighter path must not weaken that.

## Decision

`tools/quick.py new` adds one task with `track: quick` to `board.json` and writes its brief, after `core/quick.py` accepts the request; the task then runs through the same state machine, gates, review and handoff as any other, and no station opens or closes.

## Entry rule (core/quick.py)

Accepted only when all hold:

- the line's build station is closed (a shipped or at least built product);
- the scope names existing files only and no dependency manifest or protected path;
- the request changes no platform, trait, data model file or must item's evidence;
- at most one quick task is in progress.

Otherwise refused with the reason and the next path: `pl_change new` for a change proposal.

## Consequences

- **Positive:** small changes cost one task; no second definition of done; the stop check and guard work as before.
- **Negative:** the rule needs the data model and evidence paths to be known, which `factory.json` and `docs/module-map.md` provide; an edge case may be refused and go through a proposal.
- **Binds:** `core/quick.py`, `tools/quick.py`, `core/board.py` (schema: optional `track`), `templates/board.schema.json`, `pl_quick`.
- **Prevents:** a back door around gates and review.

## Alternatives

- **A separate light state machine** — rejected: two definitions of done.
- **No quick track, everything through proposals** — rejected: a typo fix would need an approval.
