# Architecture: <package>

> Profile L: copy to `<package>/ARCHITECTURE.md` for every package created in stage 1. Max. 400 words. Only what is true for this package; system-wide rules stay in the root `ARCHITECTURE.md`.

**As of:** <YYYY-MM-DD> · **Kind:** <package | service | app | tool | infra> · **Owner:** <role>

## Purpose

<1–2 sentences: what does the package do, for whom inside the system, what is explicitly not its job.>

## Inputs

- <data, calls, events, config it receives; source package or contract>

## Outputs

- <data, calls, events, files it produces; consuming package or contract>

## Invariants

> Only rules two independently built modules of this package would otherwise decide differently. Reference a root `AD-n` where the rule comes from there.

| ID | Rule | Prevents |
| --- | --- | --- |
| P-1 | <one sentence> | <class of errors> |
| P-2 | <...> | <...> |

## Allowed imports

- `may_import` from `board.json`: `<package paths only>`.
- No other package, no deep import into another package's internals. Contracts are the exception.
- Gate: `boundaries` (see root `AGENTS.md`).

## Commands

- **Build:** `<command from the package manifest>` → <expected>
- **Tests:** `<command>` → <expected>
- **Lint/types:** `<command>` → <expected>

## Links

- Root: `ARCHITECTURE.md` (`AD-n`), `docs/module-map.md`
- Contracts: `docs/contracts/<...>.md`
