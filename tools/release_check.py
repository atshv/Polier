#!/usr/bin/env python3
"""Release gate: release only a clean, tagged, merged and finished state.

Usage:
    python3 tools/release_check.py [root] [--allow-untagged] [--base BRANCH] [--json]

Read-only: the check runs `git` and reads files, it never changes the checkout.
Findings (exit 1):

1. the working tree is dirty — every file `git status --porcelain` reports is
   named; commit or discard it before releasing;
2. HEAD is not a tag — the release commit must be tagged (`v<version>`). With
   `--allow-untagged` (previews) this is a warning instead of an error;
3. the tag's commit is not an ancestor of the base branch — a release must sit
   on the trunk. Base branch: `--base`, else `board.json` → `base_branch`, else
   `main`. A missing base branch is a finding (the merge cannot be verified);
4. a task of a released stage is not `done`.

A stage (schema 1.0 `stages`) is *released* when both hold:

- `owner_decision` is `"continue"` (a stage without a decision is not released),
- every gate named in `exit_gates` has at least one passing record in
  `reviews/evidence/*.json`. Passing means `exit_code` 0 and, when the PL-03
  `result` field is present, not `fail`, `infra`, `busy` or `timeout`.
  A stage without `exit_gates` counts as released.

Boards without `stages` (0.9) skip rule 4. A missing or unreadable board.json
only warns; the git checks still run.

Exit 0 = no findings (warnings allowed), 1 = at least one finding,
2 = usage or environment error (no git repository). Offered as the standard
gate name `release-clean`; no external dependencies, Python 3.9+.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.board import load_board, stage_key  # noqa: E402

VERSION_TAG = re.compile(r"^v?[0-9]+\.[0-9]+\.[0-9]+$")
EVIDENCE = Path("reviews") / "evidence"
NON_PASSING = {"fail", "infra", "busy", "timeout"}


def _git(root, *args: str):
    """Run git in `root`; None when git is not installed."""
    try:
        return subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None


def _git_status_bytes(root):
    """`git status --porcelain -z` as bytes, or None when git is unavailable."""
    try:
        return subprocess.run(["git", "-C", str(root), "status", "--porcelain=v1", "-uall", "-z"],
                              capture_output=True, check=False)
    except FileNotFoundError:
        return None


def _is_repo(root) -> bool:
    result = _git(root, "rev-parse", "--is-inside-work-tree")
    return result is not None and result.returncode == 0 and result.stdout.strip() == "true"


def _head(root) -> Optional[str]:
    result = _git(root, "rev-parse", "--verify", "HEAD")
    if result is None or result.returncode != 0:
        return None
    commit = result.stdout.strip()
    return commit or None


def _changed_files(root) -> Optional[List[str]]:
    """Paths of the dirty working tree (modified, staged, untracked, deleted, renames)."""
    result = _git_status_bytes(root)
    if result is None or result.returncode != 0:
        return None
    fields = result.stdout.decode("utf-8", errors="replace").split("\0")
    paths: List[str] = []
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        paths.append(path)
        if "R" in status or "C" in status:  # rename/copy: the old path follows
            if index < len(fields) and fields[index]:
                paths.append(fields[index])
            index += 1
    return paths


def _pick_tag(tags: List[str]) -> Optional[str]:
    """One deterministic tag: a version-like tag first, then alphabetically."""
    if not tags:
        return None
    versions = [tag for tag in tags if VERSION_TAG.match(tag)]
    return sorted(versions or tags)[0]


def _tag_at(root, commit: str) -> Optional[str]:
    result = _git(root, "tag", "--points-at", commit)
    if result is None or result.returncode != 0:
        return None
    return _pick_tag([line.strip() for line in result.stdout.splitlines() if line.strip()])


def _passing_gates(root) -> set:
    """Gate names that have at least one passing record in reviews/evidence/."""
    passed = set()
    folder = Path(root) / EVIDENCE
    if not folder.is_dir():
        return passed
    for path in sorted(folder.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if not isinstance(record, dict) or record.get("exit_code") != 0:
            continue
        if record.get("result") in NON_PASSING:
            continue
        gate = record.get("gate")
        if isinstance(gate, str) and gate:
            passed.add(gate)
    return passed


def released_stage_errors(root, board: dict) -> List[str]:
    """Tasks of released stages that are not `done` (the rule is in the module docstring)."""
    errors: List[str] = []
    stages = board.get("stages")
    if not isinstance(stages, list) or not stages:
        return errors
    tasks = [task for task in board.get("tasks", []) if isinstance(task, dict)]
    passed = _passing_gates(root)
    for stage in stages:
        if not isinstance(stage, dict) or stage.get("owner_decision") != "continue":
            continue
        gates = [gate for gate in stage.get("exit_gates") or [] if isinstance(gate, str) and gate]
        if [gate for gate in gates if gate not in passed]:
            continue  # exit gates are not met yet: the stage is not released
        sid = stage.get("id")
        key = stage_key(sid)
        for task in tasks:
            if stage_key(task.get("stage")) != key or task.get("status") == "done":
                continue
            errors.append(
                f"stage {sid!r} is released (owner_decision continue, exit gates passed), "
                f"but task {task.get('id')} is {task.get('status')!r} — a released stage needs every task done")
    return errors


def _load_board(root, board) -> Tuple[Optional[dict], List[str]]:
    """(board, warnings); never fails. Uses the shared reader from core.board."""
    if board is not None:
        if isinstance(board, dict):
            return board, []
        return None, ["board is not an object — released-stage check skipped"]
    loaded = load_board(root, strict=False)
    if loaded is None:
        return None, ["board.json is missing or invalid — released-stage check skipped"]
    return loaded, []


def check(root, board=None, allow_untagged: bool = False, base_branch=None) -> dict:
    """Release findings for the git repository at `root` as
    {ok, errors, warnings, tag, commit, base_branch}. Never raises."""
    root = Path(root).resolve()
    result = {"ok": False, "errors": [], "warnings": [], "tag": None,
              "commit": None, "base_branch": None}
    errors, warnings = result["errors"], result["warnings"]

    if not _is_repo(root):
        errors.append(f"not a git repository (or git is not installed): {root} — "
                      "release_check needs the project's git history")
        return result

    commit = _head(root)
    if commit is None:
        errors.append("HEAD cannot be resolved — the repository has no commits; commit and tag the release first")
        return result
    result["commit"] = commit

    loaded, board_warnings = _load_board(root, board)
    warnings.extend(board_warnings)
    board = loaded or {}
    base = base_branch or board.get("base_branch") or "main"
    if not isinstance(base, str) or not base.strip():
        base = "main"
    result["base_branch"] = base

    changed = _changed_files(root)
    if changed is None:
        errors.append("git status failed — cannot verify that the working tree is clean")
    elif changed:
        shown = ", ".join(changed[:20]) + (f" (+{len(changed) - 20} more)" if len(changed) > 20 else "")
        errors.append(f"working tree is dirty: commit or discard {len(changed)} changed file(s) "
                      f"before releasing: {shown}")

    tag = _tag_at(root, commit)
    result["tag"] = tag
    if tag is None:
        if allow_untagged:
            warnings.append("HEAD is not tagged — allowed for previews with --allow-untagged; "
                            "tag the release commit for a real release")
        else:
            errors.append("HEAD is not tagged — tag the release commit (`git tag v<version>`) "
                          "or use --allow-untagged for a preview")

    if tag is not None:
        base_rev = _git(root, "rev-parse", "--verify", f"{base}^{{commit}}")
        if base_rev is None or base_rev.returncode != 0:
            errors.append(f"base branch {base!r} not found — cannot check that tag {tag!r} is merged "
                          "into it (pass --base BRANCH)")
        else:
            ancestor = _git(root, "merge-base", "--is-ancestor", commit, base)
            if ancestor is not None and ancestor.returncode == 1:
                errors.append(f"tag {tag!r} (commit {commit[:10]}) is not an ancestor of base branch "
                              f"{base!r} — release from {base} only")
            elif ancestor is None or ancestor.returncode != 0:
                message = (ancestor.stderr.strip() if ancestor is not None else "git not available")
                errors.append(f"git merge-base failed while checking tag {tag!r} against {base!r}: "
                              f"{message or 'unknown error'}")

    errors.extend(released_stage_errors(root, board))
    result["ok"] = not errors
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Release gate: clean working tree, tagged HEAD on the base branch, "
                    "released stages done.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("root", nargs="?", default=".", help="project folder (default: current folder)")
    parser.add_argument("--allow-untagged", action="store_true",
                        help="allow an untagged HEAD (previews); warning instead of an error")
    parser.add_argument("--base", metavar="BRANCH", default=None,
                        help="base branch (default: board.json base_branch, else main)")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"error: project folder not found: {root}", file=sys.stderr)
        return 2
    if not _is_repo(root):
        print(f"error: not a git repository: {root}", file=sys.stderr)
        return 2

    result = check(root, allow_untagged=args.allow_untagged, base_branch=args.base)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for warning in result["warnings"]:
            print(f"WARN: {warning}")
        for error in result["errors"]:
            print(f"ERROR: {error}")
        if result["ok"]:
            tag = f"tag {result['tag']}" if result["tag"] else "untagged HEAD (allowed)"
            print(f"RELEASE OK: {root}: {tag}; base branch {result['base_branch']}.")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
