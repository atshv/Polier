# UX Flows: <Project name>

> Station 3 (design). Copy to `docs/ux-flows.md`. Flows and screens with numbers belong here; tokens and states belong in `docs/design-rules.md`. The headings are factory evidence anchors.

## Flows

### F1 — <story US1>

1. `<Screen A>`: user taps `<…>`
2. `<Screen B>`: shows `<…>`; error path → `<Screen E>` with `<message>`
3. Done when `<observable result>`.

## Screens

| Screen | Purpose | Main elements | States | Wireframe |
| --- | --- | --- | --- | --- |
| `<Home>` | `<…>` | `<list, add button>` | empty, loading, error, offline | `<docs/design/home.png or ASCII below>` |

## Onboarding

- First run: `<steps>`.
- Permission prompts, each asked when first needed, with its reason text: `<camera — "to scan the type plate">`.

## Prototype

- Tested with `<n>` people on `<date>`; findings and what changed.

## Commands

> CLI projects: the command interface instead of screens.

| Command | Flags | Output | Exit codes |
| --- | --- | --- | --- |
| `<tool add <url>>` | `<--title>` | `<id on stdout; --json object>` | `<0 ok, 1 duplicate, 2 usage>` |
