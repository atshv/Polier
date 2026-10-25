# ADR-0001 — Monorepo with four workspace packages

**Status:** accepted · **Date:** 2026-10-17 · **Deciders:** project team

## Context

The editor needs a native-speed scene core, a reusable component library, a shared sync service and a web app. Each part has its own build toolchain: CMake/Emscripten for the engine, TypeScript and npm for the rest. The team plans work in stages and runs several agents in parallel.

## Decision

Split the product into four workspace folders, each with its own manifest, `ARCHITECTURE.md` and build:

- `packages/engine` — C++17 core compiled to WebAssembly (kind `package`).
- `packages/ui-kit` — React components and design tokens (kind `package`).
- `services/sync` — Node sync service (kind `service`).
- `apps/web` — Next.js app (kind `app`).

The dependency direction is one way: app → UI kit → engine, app → service, service → engine. Packages never import each other's internals; cross-package data is the state contract.

## Consequences

- Each package has a small context: root files plus its own files. Briefs stay under the word budget.
- The boundaries gate can enforce the direction mechanically; a violation names file and line.
- The engine team and the product team can work in parallel once the contract is fixed.
- Cost: one more build to wire in CI, and the contract must be versioned from day one.

## Alternatives

- Single Next.js repository with the engine inlined: fastest start, but the engine build would own the app's toolchain and parallel work would collide.
- Separate repositories: strongest isolation, but cross-repository versioning is heavier than the team's size justifies.
