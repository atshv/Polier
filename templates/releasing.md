# Releasing: <Project name>

> Operations template. Copy to `docs/releasing.md`; delete sections the project does not deploy. Agents never publish — releases run in CI from tags.

## Flow

- Trunk-based: `main` is always green and deployable. Task branches are short-lived (`task/<ID>`); the lead merges one task per commit.
- No release branch and no long-lived `develop`.

## Tags

- Annotated tag `v<semver>` on `main` only, e.g. `v1.4.0`, created from the release commit.
- Never move, reuse or force-push a tag. A broken release gets a new patch tag.

## Release

1. CI runs on the tag: build, all gates, release checks. Nothing is published before they pass.
2. Never publish from a working folder: no upload, `npm publish` or copy from a laptop, a dirty checkout or a worktree.
3. Only the owner (or the release engineer named on the board) creates a tag or approves a deploy. Agents may prepare the PR, never publish.

## Environments

- Every PR gets a preview deployment of its branch. Previews use preview data, never production data.
- Staging first: deploy the tag to staging, run the smoke check, then the owner approves production.
- Production deploys the same tag or artifact that passed staging. No rebuild between staging and production.

## Rollback

- Redeploy the previous tag. If the release commit is wrong, `git revert` it on `main` and tag a patch.
- Never re-tag the broken version; record the rollback in `CHANGELOG.md`.

## Release check

1. `python3 <package>/tools/release_check.py` → exit 0: clean tree, HEAD is a tag on the base branch, released stages done.
2. All gates green in CI; every dependency pinned in `docs/versions.md`, no `[UNVERIFIED]`.
3. `CHANGELOG.md` entry for the version, with migration steps if users must change something.
4. Smoke after every deploy: `python3 <package>/tools/smoke.py --url <environment-url> --expect-status 200 --path /login --path /` → exit 0. Previews add `--header "Authorization: env:PREVIEW_TOKEN"`.
5. `docs/environments.md` checklist complete; a missing variable is a deployment failure, not a retry.
