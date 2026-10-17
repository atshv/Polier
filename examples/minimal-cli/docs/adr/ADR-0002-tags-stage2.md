# ADR-0002: Tags only in stage 2

**Date:** 2026-10-17 · **Status:** accepted · **Supersedes:** –

## Context

Tags matter for daily use, but they touch service, store and CLI. M03 (add/list/search) is the MVP core. If tags moved into M03, the task would grow beyond complexity 5 and the review surface would increase.

## Decision

M03 stays with add/list/search without tags. Tags come as M04 in stage 2, once the MVP core is green.

## Consequences

- **Positive:** M03 stays small and testable; the MVP is usable earlier.
- **Negative:** `bm add --tag` only works from stage 2.
- **Binds:** M03, M04
- **Prevents:** an overloaded first task.

## Alternatives

- **Tags in M03** — rejected: task too large, mixed acceptance.
- **No tags at all** — rejected: filters are a core benefit.
