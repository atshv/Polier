# Security

Polier keeps honest agents inside their task; it is not a sandbox. The known gaps are listed in [`docs/guard-limits.md`](docs/guard-limits.md) and are not vulnerabilities.

Please report privately, through GitHub's **Report a vulnerability** on this repository, anything that lets an agent:

- write outside its task's scope through a guarded file tool,
- close a station, take lead mode or grant an approval without the owner's answer in the approval prompt,
- run a command the project's `policy.json` denies,
- or make the plugin execute something other than the package's own Python tools.

Include the harness version (DSH or Claude Code), the Polier version and the steps. Supported is the latest release.
