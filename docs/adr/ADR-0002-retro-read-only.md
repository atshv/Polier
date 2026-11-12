# ADR-0002: The retro reads project records read-only and reports locally

**Date:** 2026-11-12 · **Status:** proposed · **Supersedes:** –

## Context

F2 turns the records of real projects into named error classes (US2, D2). The records already exist in every project: `runs/<ID>.json` (attempts, checkpoints), `reviews/<ID>.md` (rounds, verdicts), `reviews/evidence/` (gate records), `reviews/approvals/`, `board.json` (statuses, open questions) and `factory.json` (deferred and n/a items, events). Projects can hold private data; Polier has no service and no telemetry.

## Decision

`tools/retro.py` reads the folders the maintainer names, never writes into them, and prints or writes one report to a path the maintainer names; `core/retro.py` holds one function per error class, each returning count, an example record path and the Polier file the class points at.

## First error classes

| Class | Signal in the records | Points at |
| --- | --- | --- |
| repeated gate failure | same gate failing in ≥ 2 attempts of a task | `templates/gates/<stack>.md`, brief template |
| long review | > 1 review round, grouped by the reviewer's finding headings | `prompt/rubric.md`, role instructions |
| scope pressure | `open_questions` or stop-check reports about paths outside the scope | `prompt/generator.md` plan rules, `templates/task-brief.md` |
| deferred or n/a must-near item | items deferred or marked n/a across projects | `factory/catalog.json` |
| stalled approval | approvals pending longer than a stage | `prompt/orchestration.md` |
| busy or infra gate | `busy`, `infra`, `timeout` gate records | `templates/gates/`, slot docs |

## Consequences

- **Positive:** no data leaves the machine; uses records Polier already writes; each finding names the file to change, which fits "change the generator only for a named class of errors".
- **Negative:** only as good as the records; projects without `runs/` give little.
- **Binds:** `core/retro.py`, `tools/retro.py`.
- **Prevents:** a retro that edits or uploads projects.

## Alternatives

- **Opt-in telemetry** — rejected: a service, accounts and a privacy burden for a tool with no backend.
- **LLM summary of transcripts** — rejected as the base: not reproducible; may come later on top of the counted classes.
