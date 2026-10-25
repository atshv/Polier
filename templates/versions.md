# Versions: <Project name>

> Copy to `docs/versions.md`. Every dependency in every manifest appears here. `[UNVERIFIED]` never belongs in a release.

| Tool / library | Exact version | Source URL | Date checked | Approved by |
| --- | --- | --- | --- | --- |
| `<runtime>` | `<x.y.z>` | `<URL>` | <YYYY-MM-DD> | <role> |
| `<framework>` | `<x.y.z>` | `<URL>` | <YYYY-MM-DD> | <role> |
| `<database / driver>` | `<x.y.z>` | `<URL>` | <YYYY-MM-DD> | <role> |
| `<compiler / SDK>` | `<x.y.z>` | `<URL>` | <YYYY-MM-DD> | <role> |
| `<tool in CI>` | `<x.y.z>` | `<URL>` | <YYYY-MM-DD> | <role> |

## Rules

1. Every dependency from `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `CMakeLists.txt`, lockfiles and CI workflows appears here, including dev dependencies, browsers and build tools.
2. Versions are exact and come from the manifest or lockfile, or from upstream release notes with a URL. Record the date (`YYYY-MM-DD`) and who checked it.
3. `[VERIFY: from manifest/docs]` marks a value still to confirm; `[UNVERIFIED]` marks an unconfirmed claim. Resolve both before tagging — neither belongs in a release.
4. A version change updates the manifest, the lockfile and this table in the same task. No silent upgrades, no `latest`.
5. Profile L: `tools/check.py` warns about a manifest dependency missing here; treat the warning as an error before release.
