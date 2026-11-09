# Releasing: canvas-mini

> Operations document. Agents never publish — releases run in CI from tags.

## Flow

- Trunk-based: `main` is always green and deployable. Task branches are short-lived (`task/<ID>`); the lead merges one task per commit.
- No release branch and no long-lived `develop`.

## Tags

- Annotated tag `v<semver>` on `main` only, created from the release commit, e.g. `v0.1.0`.
- Never move, reuse or force-push a tag. A broken release gets a new patch tag.

## Release

1. CI runs on the tag: engine build, WASM build and size gate, package tests, e2e, release check. Nothing is published before they pass.
2. Never publish from a working folder: no upload, `npm publish` or copy from a laptop, a dirty checkout or a worktree.
3. Only the owner creates a tag or approves a deploy. Agents may prepare the pull request, never publish.

## Environments

- Every pull request gets a preview deployment of its branch. Previews use preview data, never production data.
- Staging first: deploy the tag to staging, run the smoke check, then the owner approves production.
- Production deploys the same tag or artifact that passed staging. No rebuild between staging and production. See `docs/environments.md`.

## Rollback

- Redeploy the previous tag. If the release commit is wrong, `git revert` it on `main` and tag a patch.
- Never re-tag the broken version; record the rollback in `CHANGELOG.md`.

## Release check

1. `python3 .generator/tools/release_check.py --allow-untagged` → exit 0: clean tree, HEAD on the base branch (a tag for a real release), all released stages complete.
2. All gates green in CI; every dependency pinned in `docs/versions.md`, no `[UNVERIFIED]` and no open `[VERIFY: …]`.
3. `CHANGELOG.md` entry for the version, with migration steps if users must change something.
4. Smoke after every deploy: `python3 .generator/tools/smoke.py --url <environment-url> --expect-status 200 --path /` → exit 0.
5. `docs/environments.md` checklist complete; a missing variable is a deployment failure, not a retry.

## Stage decisions

- Stage `engine-spike` ends with an owner decision: `continue` only when `cpp-unit` and `wasm-build` records exist and the WASM size is within budget; otherwise `stop` and no dependent stage starts.
- The decision is edited in `board.json` (`stages[].owner_decision`) and `STATUS.md` is regenerated. Never hand-edit `STATUS.md`.
