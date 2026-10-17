# Architecture: <Project name>

**As of:** <YYYY-MM-DD> · **Status:** binding · **Owner:** <role>

> **Size budget:** 400–600 words, hard limit 800. If you need more: move it out and link it, don't append.

## 1. Purpose and non-goals

<2–3 sentences: what does the system do, for whom, what is the value?>

**Non-goals:** <what is deliberately out>

## 2. Hard constraints

- **Platform/version:** <...>
- **Data and network:** <offline, no API, ...>
- **Legal/rules:** <ToS, privacy, licences>
- **Secrets/backend:** <no backend; no secrets in the bundle | backend, secrets server-side>
- **Time/budget:** <...>
- **Language:** UI <English>, code/prompts <English>

## 3. System shape and module structure

<Layers and allowed dependency direction. Details: `docs/module-map.md`>

| Layer | Folder | May | May not |
| --- | --- | --- | --- |
| UI/screens | `<...>` | call logic | access data/DB directly |
| Logic | `<...>` | data/repository, own domain types | UI |
| Data/infrastructure | `<...>` | standard library/DB driver, own row types | UI, logic |

**Rule:** dependencies only point downwards: UI → logic → data; no cycles. Domain types live in the logic layer; the data layer does not import them.

## 4. Invariants (AD-1 … AD-n)

> Only decisions that two independently built modules would otherwise make incompatibly. Non-obvious, a real trade-off.

| ID | Rule | Binds | Prevents |
| --- | --- | --- | --- |
| AD-1 | <one sentence> | <modules/paths> | <class of errors> |
| AD-2 | <...> | <...> | <...> |

## 5. Boundaries and ownership

| Area | Belongs to | Write | Read |
| --- | --- | --- | --- |
| <path/module> | <layer/role> | <who> | <who> |

## 6. Quality gates

- **Build:** `<command>` → <expected>
- **Tests:** `<command>` → <expected>
- **Lint/types:** `<command>` → <expected>
- **E2E/acceptance:** <scenario> → <visible result>
- **Review:** independent; diff + criteria + gate output

## 7. Open / deliberately undecided (deferred)

- <topic> — <when it will be decided>

## 8. References

- Module structure: `docs/module-map.md`
- Data model: `docs/data-model.md`
- Contracts: `docs/contracts/<...>.md`
- Decisions: `docs/adr/`
- Domain knowledge: `docs/domain/<...>.md`
- Operations: `docs/runbook.md`
