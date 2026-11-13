# C01 — Richer briefs and an idea-collecting Polier

**Status:** draft — waits for the owner's `scope_change` approval · **Asked by:** owner, 2026-11-13 · **Format:** ADR-0003 (written by hand; `tools/change.py` does not exist yet, M06)

## Why

The owner wants Polier to help write much fuller briefs and to become far more creative: collect ideas instead of only asking for requirements.

Observed in this line:

- Polier has no divergent step. Station 1 interviews, station 2 writes the concept; rule 3 ("Ask rather than guess. No invented requirements.") and rule 8 ("Invent nothing") keep agents from proposing anything, and `roles/analyst.md` says "later ideas go under next or later, not into the plan".
- Briefs are capped at 800 words (`tools/check.py` `BUDGETS`, profile S and M). The M01 brief had to be cut from 874 to 794 words, and pitfalls and edge cases were shortened to fit.
- The first cold start of M01 found real gaps (expected outcome for six of eight cases, the gate command only by reference): the brief template did not ask for them.
- Neighbours do it: Superpowers starts with a brainstorming skill that refines a design by questioning before any code; BMAD's analyst runs structured brainstorming (`docs/research/neighbours.md`).

## What

### F10 — Rich briefs

- **Two layers.** `tasks/<ID>.md` stays the worker's must-read core. New, optional `tasks/<ID>/` dossier for everything that helps but need not be read first: worked examples, sample inputs and outputs, design options considered, test ideas, research excerpts, screenshots.
- **New brief sections** (`templates/task-brief.md`): *Intent* (the owner's story quoted, what success looks like for the user), *Worked example* (one concrete input → output), *Test ideas* (beyond acceptance: negative, boundary, property tests), *Edge-case matrix* (input × state → expected), *Options considered* (the chosen approach and the rejected ones, one line each), *Definition of excellent* (what a great result does beyond passing).
- **Budgets:** core brief 600–1500 words for S/M, 1800 for L; the dossier has no word budget but is never in the worker's mandatory context pack.
- **Drafting help:** `tools/brief.py draft <ID>` (and `pl_brief`) fills everything the records already know — goal, why, satisfies, scope and out of scope, acceptance IDs, gates with commands, context pack, handoffs of the dependencies, matching research notes, pitfalls from the retro (F2) — and leaves the creative sections for the lead with prompts. `tools/check.py` reports a ready brief whose required sections are empty.

### F11 — Ideas

- **Idea backlog** `docs/ideas.md` (`templates/ideas.md`), written through `tools/ideas.py` / `pl_ideas`: each idea has an ID, a one-line pitch, its source (owner, research, competitor, retro, eval, agent), the value it serves, a rough effort, and a status `new | chosen | parked | dropped` with the owner's reason.
- **Divergent round, then convergent** in station 1 and at the start of every new stage: the agent collects at least ten ideas from at least three sources with named techniques — "how might we" questions on the problem, a teardown of the alternatives, user-journey pain points, analogies from other domains, constraint flips ("what if it had to work offline / in one minute / for 1000 users"), one deliberately wild round, and a pre-mortem ("it failed in a year; why?"). Then it clusters and scores (value, effort, risk) and puts the top picks to the owner with `AskUserQuestion` / `ask_user_question`.
- **Rule kept, made explicit:** ideas are proposals, never requirements. Only an idea the owner chooses becomes a feature in `docs/concept.md`, with its idea ID as source. Rule 3 and rule 8 stay; the generator says that a labelled idea is not an invented requirement.
- **Feeding the backlog later:** the retro (F2), eval findings (F1) and change proposals (F3) add ideas; parked ideas come back at the next stage start.
- **Role:** a new specialist role `ideator` (stations idea, concept; model strong) that runs the rounds; the analyst keeps the concept.
- **Catalog:** new item `CON-11` *Idea backlog* (should, every platform) with evidence `docs/ideas.md`.

## Deltas to the living docs

### `docs/concept.md#features` — ADDED

| F10 | **Rich briefs**: two-layer briefs with intent, worked example, test ideas, edge-case matrix, options and a definition of excellent; `tools/brief.py draft` fills the known parts | MVP (stage 2) | fuller briefs, fewer cold-start gaps |
| F11 | **Ideas**: idea backlog, divergent and convergent rounds with named techniques, the `ideator` role, `CON-11` | MVP (stage 2) | Polier proposes and collects ideas; the owner chooses |

### `docs/concept.md#user-stories` — ADDED

- **US5** (F10) As the lead I want a drafted brief with every known fact filled in so that I spend my time on intent, examples and edge cases.
  - WHEN `tools/brief.py draft M0x` runs THEN the brief has goal, scope, acceptance IDs, gates with commands, context pack and handoffs from the records, and marks each creative section to fill.
  - WHEN a ready task's brief has an empty required section THEN `tools/check.py` names the task and the section.
- **US6** (F11) As the owner I want Polier to bring me ideas I had not thought of so that the product is better than my first description.
  - WHEN an ideation round runs THEN `docs/ideas.md` holds at least ten ideas from at least three sources, each with source and technique, and I am asked to choose.
  - WHEN I choose an idea THEN it appears in `docs/concept.md` features with its idea ID; ideas I do not choose stay `parked` or `dropped` with my reason.

### `docs/quality.md#definition-of-done` — ADDED

- **D5** A brief drafted with `tools/brief.py draft` for a fixture task passes the cold start in round 1 with no gap finding, after the lead filled only the creative sections. (US5)
- **D6** On a fresh fixture project, an ideation round yields ≥ 10 ideas from ≥ 3 sources in `docs/ideas.md`; the owner's choice moves the chosen ones into the concept with their IDs; `tools/check.py` passes. (US6)

## Proposed tasks (stage 2, after the owner's approval)

| ID | Title | Role | Scope (main paths) |
| --- | --- | --- | --- |
| M11 | Idea backlog core and command | backend-builder | `core/ideas.py`, `tools/ideas.py`, `templates/ideas.md`, tests |
| M12 | Ideation in the process: `ideator` role, techniques, `CON-11` | architect | `roles/ideator.md`, `roles/roles.json`, `factory/catalog.json`, `prompt/generator.md` (station 1 and stage start), `SKILL.md` |
| M13 | Rich brief template, budgets and the empty-section check | architect | `templates/task-brief.md`, `tools/check.py`, `prompt/generator.md` (briefs) |
| M14 | Brief drafting | backend-builder | `core/brief.py`, `tools/brief.py`, tests |
| M15 | `pl_ideas` and `pl_brief` tools | backend-builder | `plugin/lib/tools.mjs`, plugin and Claude Code tests, `docs/tools.md` |

Order: M13 before M14 (the template defines the sections), M11 before M12 and M15. M14 uses the retro (M03) when it is done and works without it.

## Approval

`scope_change` for C01, recorded with `pl_approval` (or `tools/approve.py` without a dialog) before any task of C01 starts.
