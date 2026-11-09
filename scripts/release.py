#!/usr/bin/env python3
"""Work out the next release from Conventional Commits.

Usage:
    python3 scripts/release.py [--root .] [--write] [--notes FILE] [--github-output FILE]

``VERSION`` is the source of truth. Its tag ``vX.Y.Z`` marks the last release.

- When that tag does not exist yet, it is a hand-made release: ``CHANGELOG.md``
  should have a ``## X.Y.Z`` section; without one the section is generated
  from the commits since the newest older tag.
- Otherwise the commits since the tag decide. Before 1.0 every version is a
  pre-release: a breaking change (``feat!:``, ``fix(scope)!:`` or a ``BREAKING
  CHANGE:`` footer) bumps the minor number, ``feat``, ``fix`` and ``perf`` bump
  the patch number. From 1.0 on: breaking → major, ``feat`` → minor, ``fix`` and
  ``perf`` → patch. Other types (``docs``, ``test``, ``ci``, ``chore``,
  ``refactor``, ``style``, ``build``) and non-conventional subjects release
  nothing.

``--write`` updates ``VERSION``, ``package.json`` and ``CHANGELOG.md``;
``--notes`` writes the release notes (the changelog section); and
``--github-output`` appends ``release``, ``version``, ``tag``, ``prerelease``
and ``changed`` for a GitHub Actions step. Standard library only.

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


def tags(root: Path) -> List[str]:
    return [t for t in git(root, "tag", "--merged", "HEAD", "--list", "v*").split() if SEMVER.match(t[1:])]


def newest_tag(root: Path) -> Optional[str]:
    """The most recently created release tag reachable from HEAD (for the commit range)."""
    found = tags(root)
    if not found:
        return None
    order = git(root, "for-each-ref", "--sort=-creatordate", "--format=%(refname:short)", "refs/tags").split()
    ranked = [t for t in order if t in found]
    return ranked[0] if ranked else max(found, key=parse_version)


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
    breaking = any(c["breaking"] for c in changes)
    feature = any(c["type"] == "feat" for c in changes)
    fix = any(c["type"] in ("fix", "perf") for c in changes)
    if major == 0:
        if breaking:
            return (0, minor + 1, 0)
        return (0, minor, patch + 1) if feature or fix else None
    if breaking:
        return (major + 1, 0, 0)
    if feature:
        return (major, minor + 1, 0)
    if fix:
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
    parse_version(current)
    changelog = root / "CHANGELOG.md"
    text = changelog.read_text(encoding="utf-8") if changelog.is_file() else "# Changelog\n"
    if f"v{current}" not in tags(root):
        changes = [c for c in (classify(commit) for commit in commits_since(root, newest_tag(root))) if c]
        existing = changelog_section(text, current)
        return {"release": True, "version": current, "manual": True, "changes": changes,
                "prerelease": parse_version(current)[0] == 0,
                "notes": existing or section(current, changes), "needs_section": existing is None}
    changes = [c for c in (classify(commit) for commit in commits_since(root, f"v{current}")) if c]
    nxt = bump(parse_version(current), changes)
    if nxt is None:
        return {"release": False, "version": current, "manual": False, "changes": changes, "prerelease": False,
                "notes": "", "needs_section": False}
    version = ".".join(str(part) for part in nxt)
    return {"release": True, "version": version, "manual": False, "changes": changes, "prerelease": nxt[0] == 0,
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
        pre = ", pre-release" if result.get("prerelease") else ""
        print(f"release v{result['version']} ({kind}{pre}, {len(result['changes'])} conventional commit(s))")
    else:
        print("no release: no feat, fix, perf or breaking commit since the last tag")
    if args.notes and result["release"]:
        Path(args.notes).write_text(str(result["notes"]).split("\n", 1)[1].lstrip("\n"), encoding="utf-8")
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as handle:
            handle.write(f"release={'true' if result['release'] else 'false'}\n")
            handle.write(f"version={result['version']}\n")
            handle.write(f"tag=v{result['version']}\n")
            handle.write(f"prerelease={'true' if result.get('prerelease') else 'false'}\n")
            handle.write(f"changed={'true' if changed else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
