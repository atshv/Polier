<p align="center">
  <img src="docs/images/line.svg" alt="Polier – the factory line: idea, concept, design, architecture, plan, build, verify, release, operate" width="100%">
</p>

<p align="center">
  <a href="https://github.com/atshv/Polier/releases"><img alt="release" src="https://img.shields.io/github/v/release/atshv/Polier?style=flat-square&color=6366f1"></a>
  <a href="https://github.com/atshv/Polier/actions/workflows/test.yml"><img alt="tests" src="https://img.shields.io/github/actions/workflow/status/atshv/Polier/test.yml?branch=main&style=flat-square&label=tests"></a>
  <img alt="license" src="https://img.shields.io/badge/license-MIT-34d399?style=flat-square">
  <img alt="python" src="https://img.shields.io/badge/python-3.9%2B-1f5f8b?style=flat-square">
  <img alt="dependencies" src="https://img.shields.io/badge/dependencies-none-34d399?style=flat-square">
</p>

<p align="center"><b>English</b> · <a href="README.de.md">Deutsch</a></p>

**Polier is an AI software factory.** You describe the product; Polier runs it through nine stations — idea, concept, design, architecture, plan, build, verify, release, operate — for a website, an iOS or Android app, a desktop app, a CLI or a backend service. At every station it knows what your kind of product needs (sign-up, payments, offline mode, privacy policy, App Store privacy label, Play closed test, signing, monitoring …), asks for proof and lets the station close only when you approve it.

Builder agents then work task by task inside the plan: writes outside the task are blocked, only recorded test runs count as evidence, and every attempt, review and approval is logged. Works with **Claude Code**, any **MCP** client and **DeepSeek Harness**. Python standard library only; everything stays as files in your repository.

## Quick start

```bash
git clone https://github.com/atshv/Polier.git && cd Polier
./install.sh claude          # Claude Code; DeepSeek Harness: dsh plugin --profile <name> add .
```

Open a session in an empty folder and write *"Build a new app with Polier: …"*. Polier interviews you, starts the line and walks you through the stations.

```bash
python3 tools/factory.py --root <project> status    # where the project is
python3 tools/factory.py --root <project> next      # what the current station still needs
```

## The line

| # | Station | Output | Examples of what it checks |
|---|---|---|---|
| 1 | Idea | `project-input.md`, `factory.json` | problem, users, success signal, non-goals, platforms |
| 2 | Concept | `docs/concept.md` | MVP features, user stories, done scenarios, costs, legal frame |
| 3 | Design | `docs/ux-flows.md`, `docs/design-rules.md` | flows, screens, tokens, states, accessibility, platform guidelines |
| 4 | Architecture | `ARCHITECTURE.md`, ADRs | stack with sources, layers, data model, API, secrets, environments |
| 5 | Plan | `board.json`, `policy.json`, briefs | every build and verify item linked to a task, gates, cold start |
| 6 | Build | code, `runs/`, `reviews/` | auth, data, security, payments, push, permissions, privacy manifest |
| 7 | Verify | gate evidence | E2E, device/browser matrix, accessibility, OWASP/MASVS, beta |
| 8 | Release | `docs/legal.md`, `docs/store/*` | CI from tags, legal texts, store listings, signing, notarisation |
| 9 | Operate | `docs/runbook.md` | errors, uptime, backups, support, updates, store upkeep |

The full checklist — 175 items, each with the platforms and traits it applies to — is [`factory/CATALOG.md`](factory/CATALOG.md). A web app with accounts gets about 100 of them, a CLI about 50.

## Proof, not promises

- An item is done only with evidence: a file in the project (`docs/concept.md#user-stories`) or linked tasks that are done.
- `must` items are done or *not applicable* with a reason; only `should` items can be deferred.
- A task is done only with a passing review, recorded gate runs and a handoff.
- A station closes only with every item resolved, every earlier station closed and the owner's name: `factory.py advance --by <you>`.

## What's inside

| | |
|---|---|
| **Factory** | `factory/catalog.json`, `tools/factory.py`, templates for concept, flows, legal texts, store listings and runbook |
| **Guard rails** | write guard, checkpoints, claims, approvals, token budgets — in `core/`, the same for every harness |
| **Gates** | catalogues for Node/TS, Python, Swift/iOS, Kotlin/Android, Expo, Flutter, C++, WASM, Postgres, Playwright, load, visual diff |
| **Integrations** | Claude Code hooks, DeepSeek Harness plugin (`pl_factory`, `/pl factory`), MCP server (`tools/mcp.py`) |
| **Examples** | [`factory-app`](examples/factory-app) (a line in progress), [`minimal-cli`](examples/minimal-cli), [`monorepo-mini`](examples/monorepo-mini) |

## Learn more

- **Process** — [`prompt/generator.md`](prompt/generator.md) · **Your part** — [`guide/cheatsheet.md`](guide/cheatsheet.md)
- **Connect an AI client** — `claude mcp add polier -- python3 tools/mcp.py --root <project>`
- **Limits** — Polier is not a sandbox: [what the write guard does not cover](docs/guard-limits.md)
- **Changes** — [`CHANGELOG.md`](CHANGELOG.md) · [Releases](https://github.com/atshv/Polier/releases)

Tests: `npm install && npm test`. Licence: [MIT](LICENSE).
