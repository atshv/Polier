# Research: can Polier's agent behaviour be measured in Claude Code?

**Question:** Is there a harness-native way to run scenario evals of a plugin with a no-plugin baseline?
**Asked by:** concept (feature F1)
**Date:** 2026-11-12

## Answer

Yes. Claude Code 2.1.323 ships `claude plugin eval`: it runs eval cases from `evals/` (`case.yaml`, or `prompt.md` plus `graders/*.md`) against a plugin and reports scores; with `--ablation with-without` it adds a no-plugin arm and reports the delta. Real MCP servers start only on opt-in (`--allow-real-servers`); `--trust-plugin` answers the trust question in CI. Polier's process scenarios (close a station, out-of-scope write, chat "yes" instead of an approval) fit this shape. DSH has no comparable command `[UNVERIFIED]`; there the same cases can run through the plugin test harness.

## Sources

- `claude plugin eval --help`, Claude Code 2.1.323 (checked 2026-11-12) — case layout, ablation, real-server opt-in
- https://code.claude.com/docs/en/plugin-evals.md (not read yet) — case.yaml schema and graders [VERIFY]

## Open

- The `case.yaml` schema and grader format must be read before the architecture station.
