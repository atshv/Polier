# {{ID}} — {{TITLE}}

**Status:** draft · **Asked by:** {{BY}}, {{DATE}} · **Format:** ADR-0003

<!--
A change proposal (ADR-0003). `tools/change.py new` fills the {{...}} fields; `tools/change.py link` fills the linked tasks; `tools/change.py apply` merges the deltas into the living docs once a `scope_change` approval names this ID in its note and every linked task is done.

Delta blocks go under "Deltas to the living docs", one per target, as a level-3 heading `file#heading` — KIND. The file is relative to the project root; the heading is matched like an evidence anchor (case and punctuation do not matter) and must occur exactly once in the file. Kinds:

  ADDED     the lines below the heading are appended to the end of the section (table rows after the last row, list items after the last item).
  MODIFIED  an "Old:" and a "New:" fenced block; the old text must occur exactly once under the heading and is replaced.
  REMOVED   an "Old:" fenced block; the text is removed.

Deltas apply top-down in file order; a second MODIFIED on one heading must match the text after the first.

### `docs/concept.md#features` — ADDED

| F9 | **Export** | MVP | backup |

### `docs/quality.md#definition-of-done` — MODIFIED

**Old:**
```
- **D3** old wording
```

**New:**
```
- **D3** new wording
```
-->

## Why

<what the owner asked for and what was observed; facts, not guesses>

## What

<the change in plain words; features, platforms, constraints>

## Linked tasks

none yet (`tools/change.py link {{ID}} --task M10`)

## Deltas to the living docs

## Approval

`scope_change` for {{ID}}, recorded with `pl_approval` (or `tools/approve.py` without a dialog), with `{{ID}}` in its note, before any task of {{ID}} starts.
