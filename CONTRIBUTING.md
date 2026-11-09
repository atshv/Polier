# Contributing

Thanks for helping. Everything an agent or a person needs to change Polier is in [`AGENTS.md`](AGENTS.md): the layout, the commands, the rules and how releases work.

Before you open a pull request:

1. `npm install && npm test` — all suites green.
2. `pip install pyflakes && npm run check` — generated pages current, no dead code.
3. Title and commits in Conventional Commits form (`feat(plugin): …`, `fix: …`); breaking changes with `!`.
4. In the description: what changes for a running project, which checks you ran, and what you could not verify (for example a real DeepSeek Harness session).

Ideas and bugs: open an issue with the DSH version (`dsh --version`), the Polier version (`VERSION`) and the smallest project that shows it.
