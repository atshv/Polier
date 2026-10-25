#!/usr/bin/env python3
"""Build or verify the shipped-file manifest of a Polier package.

Usage:
    python3 tools/manifest.py --write [--package PATH] [--out PATH]
    python3 tools/manifest.py --check [--package PATH] [--out PATH]

The manifest lists, for every file the package ships, its SHA-256 hash:

    {
      "version": "1.0.0",
      "generated": "2026-10-25",
      "files": {"CHANGELOG.md": "…", "tools/check.py": "…"},
      "count": 2
    }

The shipped files come from `package.json` → `files`: exact paths, globs
(`core/*.py`, `*` does not cross `/`) and folders ending in `/` (recursive).
`VERSION` and `CHANGELOG.md` are always included when they exist and are not
matched already. `__pycache__`, `node_modules`, `.git`, `.DS_Store` and `*.pyc`
are never shipped. Paths use forward slashes and are sorted; the output is
deterministic (2-space indent, trailing newline) apart from `generated`, which
follows the date, so unchanged content produces the same bytes on the same day.
The manifest file itself is not listed.

`--check` recomputes the files without writing and exits 1 when the manifest is
stale (a file changed, disappeared or was added); it exits 0 when it matches.

Exit 0 = written or in sync, 1 = drift, 2 = usage or environment error (no
package.json / VERSION, or no manifest to check). No external dependencies,
Python 3.9+.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

MANIFEST = Path("tools") / "manifest.json"
ALWAYS = ("VERSION", "CHANGELOG.md")
SKIP_DIRS = {"__pycache__", ".git", "node_modules"}
SKIP_NAMES = {".DS_Store"}
SKIP_SUFFIXES = {".pyc"}


class ManifestError(Exception):
    """Environment or configuration problem (exit 2), not drift."""


def package_dir(package=None) -> Path:
    """The package folder: `--package`, else the folder above this tools/ folder."""
    if package:
        return Path(package).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ignored(path: Path, package: Path) -> bool:
    rel = path.relative_to(package)
    if any(part in SKIP_DIRS for part in rel.parts):
        return True
    return path.name in SKIP_NAMES or path.suffix in SKIP_SUFFIXES


def _files_under(folder: Path, package: Path) -> List[str]:
    """Package-relative forward-slash paths of the shipped files below `folder`."""
    if not folder.is_dir():
        return []
    return [path.relative_to(package).as_posix()
            for path in sorted(folder.rglob("*"))
            if path.is_file() and not _ignored(path, package)]


def _glob_match(rel: str, pattern: str) -> bool:
    """Match a package-relative path against a glob; `*` stays inside one folder."""
    parts, patterns = rel.split("/"), pattern.split("/")
    if len(parts) != len(patterns):
        return False
    return all(fnmatch.fnmatchcase(part, pat) for part, pat in zip(parts, patterns))


def _glob_base(pattern: str) -> str:
    """The fixed folder prefix of a glob, before its first wildcard component."""
    fixed = []
    for part in pattern.split("/")[:-1]:
        if any(char in part for char in "*?["):
            break
        fixed.append(part)
    return "/".join(fixed)


def _expand(package: Path, pattern: str) -> List[str]:
    """Shipped files for one `package.json` → `files` entry."""
    pattern = pattern.replace("\\", "/").strip()
    while pattern.startswith("./"):
        pattern = pattern[2:]
    if not pattern or pattern.startswith(("/", "..")):
        return []
    if pattern.endswith("/"):
        return _files_under(package / pattern.rstrip("/"), package)
    if any(char in pattern for char in "*?["):
        base = package / _glob_base(pattern) if _glob_base(pattern) else package
        return [rel for rel in _files_under(base, package) if _glob_match(rel, pattern)]
    target = package / pattern
    if target.is_file():
        return [] if _ignored(target, package) else [pattern]
    return _files_under(target, package)


def load_package_json(package: Path) -> dict:
    path = package / "package.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManifestError(f"package.json not found in {package}") from exc
    except (ValueError, OSError) as exc:
        raise ManifestError(f"package.json is not readable: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError(f"package.json in {package} is not an object")
    return data


def _version(package: Path) -> str:
    try:
        version = (package / "VERSION").read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError) as exc:
        raise ManifestError(f"VERSION not found in {package}") from exc
    if not version:
        raise ManifestError(f"VERSION in {package} is empty")
    return version


def shipped_files(package: Path) -> List[str]:
    """Sorted package-relative paths of every shipped file."""
    data = load_package_json(package)
    patterns = data.get("files")
    if not isinstance(patterns, list) or not patterns:
        raise ManifestError(f"package.json in {package} has no 'files' list")
    rels: Set[str] = set()
    for pattern in patterns:
        if isinstance(pattern, str):
            rels.update(_expand(package, pattern))
    for name in ALWAYS:
        if (package / name).is_file():
            rels.add(name)
    return sorted(rels)


def build_manifest(package=None, out=None) -> dict:
    """The manifest dict for `package`; `out` is excluded so it can list itself safely."""
    package = package_dir(package)
    if not package.is_dir():
        raise ManifestError(f"package folder not found: {package}")
    target = Path(out).resolve() if out else None
    try:
        out_rel = target.relative_to(package).as_posix() if target else None
    except ValueError:
        out_rel = None
    files: Dict[str, str] = {}
    for rel in shipped_files(package):
        if out_rel and rel == out_rel:
            continue
        files[rel] = _sha256(package / rel)
    return {
        "version": _version(package),
        "generated": dt.datetime.now(dt.timezone.utc).date().isoformat(),
        "files": files,
        "count": len(files),
    }


def write_manifest(package=None, out=None) -> Path:
    """Write the manifest (default: <package>/tools/manifest.json) and return its path."""
    package = package_dir(package)
    target = Path(out).expanduser().resolve() if out else package / MANIFEST
    manifest = build_manifest(package, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return target


def check_manifest(package=None, out=None) -> dict:
    """Compare the current shipped files with the manifest on disk.

    Returns {ok, missing, modified, extra, lines}. Raises ManifestError when the
    package or the manifest itself cannot be read (there is nothing to check).
    """
    package = package_dir(package)
    if not package.is_dir():
        raise ManifestError(f"package folder not found: {package}")
    target = Path(out).expanduser().resolve() if out else package / MANIFEST
    if not target.is_file():
        raise ManifestError(f"manifest not found: {target} — run tools/manifest.py --write first")
    try:
        manifest = json.loads(target.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise ManifestError(f"manifest is not readable: {exc}") from exc
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(files, dict):
        raise ManifestError(f"manifest has no 'files' object: {target}")

    current = build_manifest(package, target)["files"]
    missing = sorted(rel for rel in files if rel not in current)
    extra = sorted(rel for rel in current if rel not in files)
    modified = sorted(rel for rel, digest in files.items()
                      if rel in current and current[rel] != digest)
    ok = not (missing or extra or modified)
    lines = [f"modified: {rel}" for rel in modified]
    lines += [f"missing: {rel}" for rel in missing]
    lines += [f"new: {rel}" for rel in extra]
    if ok:
        lines = [f"manifest OK: {len(current)} shipped files, version {manifest.get('version', '?')}"]
    else:
        lines.append(f"manifest is stale: {len(modified) + len(missing) + len(extra)} finding(s) — "
                     "run tools/manifest.py --write")
    return {"ok": ok, "missing": missing, "modified": modified, "extra": extra, "lines": lines}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Build or verify tools/manifest.json (SHA-256 of the shipped files).",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--package", default=None,
                        help="package folder (default: the folder above tools/)")
    parser.add_argument("--out", default=None,
                        help="manifest path (default: <package>/tools/manifest.json)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write the manifest")
    mode.add_argument("--check", action="store_true", help="verify without writing; exit 1 on drift")
    args = parser.parse_args(argv)

    try:
        if args.write:
            target = write_manifest(args.package, args.out)
            manifest = json.loads(target.read_text(encoding="utf-8"))
            print(f"manifest written: {target} ({manifest['count']} files, version {manifest['version']})")
            return 0
        result = check_manifest(args.package, args.out)
    except ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    for line in result["lines"]:
        print(line)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
