# Mxx — <Name>

> **Size:** 400–800 words. No brief without a context pack and gates. No boilerplate; that lives in `AGENTS.md`. Stored as `tasks/Mxx.md`.

## Goal

<One sentence: what works after this task?>

**Why:** <which later module builds on it>

**Satisfies:** <D1, D2 — definition-of-done items from `docs/quality.md`, as in board.json>

## Scope

- <feature 1>
- <feature 2>

## Out of scope

- <deliberately excluded> (comes in Mxx)

## Acceptance

A1 WHEN <situation>, THEN the system SHALL <behaviour>.
A2 WHEN <situation>, THEN the system SHALL <behaviour>.
A3 ...

## Context pack

**Read exactly:**

- `ARCHITECTURE.md`, `AGENTS.md`, `STATUS.md`, `docs/module-map.md`
- `docs/contracts/<...>.md`, section <...>
- `src/<...>`, lines <...>
- `<reference file>`

**Do not read:** <other task briefs, details, ...>

**Budget:** ≤ <n> tokens input.

## Specifications

- **Layer/module:** <UI/logic/data> — `<folder>`
- **Data/contract:** <fields, types, limits, according to ARCHITECTURE.md>
- **New files:** `<path>`
- **Changed files:** `<path>` — <what exactly>
- **Reference:** `<existing file>`
- **Package:** `packages/<name>` — profile L only. This task's `scope_write` stays inside the package; contract paths from `board.json` are the only exception.

## UI specification

> Required when the task changes a UI path; otherwise delete the section. Cite tokens from `docs/design-rules.md`. **A UI task without numbers is not ready.**

| Element | Property | Value | Token |
| --- | --- | --- | --- |
| `<element>` | `<height / gap / duration>` | `<32 px / 120 ms>` | `<--control-h>` |

**States:** specify each applicable state with its visual change in px/ms/tokens: rest, hover, pressed, focus, selected, dragging, disabled, saving, error. Write `n/a` for states that cannot occur.

**Do not:** <e.g. no new hex colours, no layout animation, no focus removal, no text below 11 px, no other views changed>

**Evidence screenshots:** `reviews/evidence/<ID>-<view>-before-<viewport>.png` and `…-after-…`, at <1440×900> and <390×844>. Screenshot only the changed view.

## Pitfalls

- <quirk of a library or version> (source: <URL>, checked <date>)
- <trap in the project, e.g. field X has a different name in the DB>

## Edge cases

- <empty input, duplicate, invalid value, missing connection, double click ...>

## Gates

1. `<command>` → <expected>
2. `<command>` → <expected>
3. <E2E scenario> → <visible result>

A gate passes when command, exit code and expected output match; the output is the evidence. The task passes when all gates are green, every acceptance criterion is evidenced and the reviewer gives `pass` with no blockers.

If a gate fails: read the cause, fix the code, rerun the gate. Never adjust the test to make it pass.

## Limits

- **Scope:** only `<paths>` — inside the task's package; contract paths are the only exception
- **Stop:** <max. rounds/time/tokens>; when blocked, `status: blocked` + reason
- No architecture change; no new dependencies without approval

## Output (YAML, no prose)

```yaml
task_id: Mxx
status: submitted   # submitted | blocked | failed
changed_files: []
evidence: []        # [{gate, command, exit_code, output_tail}]
acceptance: []      # [{id, passed, how}]
open_questions: []
```
