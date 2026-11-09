#!/usr/bin/env python3
"""Work out the next release from Conventional Commits.

Usage:
    python3 scripts/release.py [--root .] [--write] [--notes FILE] [--github-output FILE]

The last release is the highest ``vX.Y.Z`` tag reachable from HEAD.

- When ``VERSION`` is already ahead of that tag, it is a hand-made release:
  ``CHANGELOG.md`` must have a ``## X.Y.Z`` section; without one the section
  is generated from the commits.
- Otherwise the commits since the tag decide: a breaking change (``feat!:``,
  ``fix(scope)!:`` or a ``BREAKING CHANGE:`` footer) bumps major (minor before
  1.0), ``feat`` bumps minor, ``fix`` and ``perf`` bump patch. Other types
  (``docs``, ``test``, ``ci``, ``chore``, ``refactor``, ``style``, ``build``)
  and non-conventional subjects release nothing.

``--write`` updates ``VERSION``, ``package.json`` and ``CHANGELOG.md``;
``--notes`` writes the release notes (the changelog section); and
``--github-output`` appends ``release``, ``version``, ``tag`` and ``changed``
for a GitHub Actions step. Standard library only.

Exit codes: 0 ok (with or without a release), 2 usage or repository error.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SUBJECT = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?(?P<bang>!)?: (?P<desc>\S.*)$")
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
RELEASE_SUBJECT = re.compile(r"^chore\(release\)")
GROUPS = (("breaking", "Breaking changes"), ("feat", "Features"), ("fix", "Fixes"), ("perf", "Performance"))


class ReleaseError(Exception):
    pass


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise ReleaseError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def parse_version(text: str) -> Tuple[int, int, int]:
    match = SEMVER.match(text.strip().lstrip("v"))
    if not match:
        raise ReleaseError(f"not a version: {text!r}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def last_tag(root: Path) -> Optional[str]:
    tags = [t for t in git(root, "tag", "--merged", "HEAD", "--list", "v*").split() if SEMVER.match(t[1:])]
    return max(tags, key=parse_version) if tags else None


def commits_since(root: Path, tag: Optional[str]) -> List[Dict[str, str]]:
    span = f"{tag}..HEAD" if tag else "HEAD"
    raw = git(root, "log", span, "--no-merges", "--format=%H%x1f%s%x1f%b%x1e")
    out = []
    for record in raw.split("\x1e"):
        record = record.strip("\n")
        if not record.strip():
            continue
        sha, subject, body = (record.split("\x1f") + ["", ""])[:3]
        out.append({"sha": sha.strip(), "subject": subject.strip(), "body": body.strip()})
    return out


def classify(commit: Dict[str, str]) -> Optional[Dict[str, object]]:
    """The conventional parts of a commit, or None for a subject that is not one."""
    if RELEASE_SUBJECT.match(commit["subject"]):
        return None
    match = SUBJECT.match(commit["subject"])
    if not match:
        return None
    note = ""
    for line in commit["body"].splitlines():
        if line.startswith(("BREAKING CHANGE:", "BREAKING-CHANGE:")):
            note = line.split(":", 1)[1].strip()
    return {
        "type": match.group("type"),
        "scope": match.group("scope"),
        "desc": match.group("desc").strip(),
        "breaking": bool(match.group("bang")) or bool(note),
        "note": note,
        "sha": commit["sha"][:7],
    }


def bump(current: Tuple[int, int, int], changes: List[Dict[str, object]]) -> Optional[Tuple[int, int, int]]:
    major, minor, patch = current
    if any(c["breaking"] for c in changes):
        return (major, minor + 1, 0) if major == 0 else (major + 1, 0, 0)
    if any(c["type"] == "feat" for c in changes):
        return (major, minor + 1, 0)
    if any(c["type"] in ("fix", "perf") for c in changes):
        return (major, minor, patch + 1)
    return None


def section(version: str, changes: List[Dict[str, object]]) -> str:
    lines = [f"## {version}", ""]
    for key, title in GROUPS:
        if key == "breaking":
            picked = [c for c in changes if c["breaking"]]
        else:
            picked = [c for c in changes if c["type"] == key and not c["breaking"]]
        if not picked:
            continue
        lines += [f"**{title}**", ""]
        for change in picked:
            scope = f"**{change['scope']}:** " if change["scope"] else ""
            note = f" — {change['note']}" if key == "breaking" and change["note"] else ""
            lines.append(f"- {scope}{change['desc']}{note} ({change['sha']})")
        lines.append("")
    if len(lines) == 2:
        lines += ["Maintenance release.", ""]
    return "\n".join(lines)


def changelog_section(text: str, version: str) -> Optional[str]:
    match = re.search(rf"^## {re.escape(version)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not match or not match.group(1).strip():
        return None
    return f"## {version}\n{match.group(1).rstrip()}\n"


def insert_section(text: str, block: str) -> str:
    match = re.search(r"^## ", text, re.M)
    if not match:
        return text.rstrip("\n") + "\n\n" + block.rstrip("\n") + "\n"
    return text[:match.start()] + block.rstrip("\n") + "\n\n" + text[match.start():]


def plan(root: Path) -> Dict[str, object]:
    version_file = root / "VERSION"
    current = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else "0.0.0"
    tag = last_tag(root)
    released = parse_version(tag) if tag else (0, 0, 0)
    changes = [c for c in (classify(commit) for commit in commits_since(root, tag)) if c]
    changelog = root / "CHANGELOG.md"
    text = changelog.read_text(encoding="utf-8") if changelog.is_file() else "# Changelog\n"
    if parse_version(current) > released:
        version = current
        existing = changelog_section(text, version)
        return {"release": True, "version": version, "manual": True, "changes": changes,
                "notes": existing or section(version, changes), "needs_section": existing is None}
    nxt = bump(released, changes)
    if nxt is None:
        return {"release": False, "version": current, "manual": False, "changes": changes, "notes": "", "needs_section": False}
    version = ".".join(str(part) for part in nxt)
    return {"release": True, "version": version, "manual": False, "changes": changes,
            "notes": section(version, changes), "needs_section": True}


def write(root: Path, result: Dict[str, object]) -> bool:
    """Apply a planned release to VERSION, package.json and CHANGELOG.md; True when a file changed."""
    if not result["release"]:
        return False
    version = str(result["version"])
    changed = False
    version_file = root / "VERSION"
    if not version_file.is_file() or version_file.read_text(encoding="utf-8").strip() != version:
        version_file.write_text(version + "\n", encoding="utf-8")
        changed = True
    package = root / "package.json"
    if package.is_file():
        data = json.loads(package.read_text(encoding="utf-8"))
        if data.get("version") != version:
            data["version"] = version
            package.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            changed = True
    if result["needs_section"]:
        changelog = root / "CHANGELOG.md"
        text = changelog.read_text(encoding="utf-8") if changelog.is_file() else "# Changelog\n"
        changelog.write_text(insert_section(text, str(result["notes"])), encoding="utf-8")
        changed = True
    return changed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Next release from Conventional Commits.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--write", action="store_true", help="update VERSION, package.json and CHANGELOG.md")
    parser.add_argument("--notes", help="write the release notes to this file")
    parser.add_argument("--github-output", help="append release, version, tag and changed to this file")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        result = plan(root)
        changed = write(root, result) if args.write else False
    except (ReleaseError, OSError, ValueError) as exc:
        print(f"release.py: {exc}", file=sys.stderr)
        return 2
    if result["release"]:
        kind = "hand-made" if result["manual"] else "from commits"
        print(f"release v{result['version']} ({kind}, {len(result['changes'])} conventional commit(s))")
    else:
        print("no release: no feat, fix, perf or breaking commit since the last tag")
    if args.notes and result["release"]:
        Path(args.notes).write_text(str(result["notes"]).split("\n", 1)[1].lstrip("\n"), encoding="utf-8")
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as handle:
            handle.write(f"release={'true' if result['release'] else 'false'}\n")
            handle.write(f"version={result['version']}\n")
            handle.write(f"tag=v{result['version']}\n")
            handle.write(f"changed={'true' if changed else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
