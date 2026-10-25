#!/usr/bin/env python3
"""Detect drift between a project's Polier copy and the manifest it was shipped with.

Usage:
    python3 tools/drift.py [root] [--json] [--package PATH]

A project keeps its Polier copy in `.generator/`; that copy ships
`tools/manifest.json` with the SHA-256 of every shipped file. `drift(root)`
checks only that project-local copy: it returns status `"no-package"` (and no
warning) when `<root>/.generator` does not exist, so a normal project stays
silent. The plugin/skill folder that runs this file is never checked
automatically — use `--package PATH` / `drift(root, package=PATH)` for it.

The manifest comparison:

- equal hashes: status `"ok"`, no warning;
- a file was edited or is missing: status `"modified"`, the files are named and
  the warning says "local edits or outdated copy";
- the copy has no readable manifest (e.g. installed before 1.0): status
  `"missing-manifest"` with a warning — never an error;
- no project-local Polier copy: status `"no-package"`, warnings empty.

Extra files that the manifest does not list are ignored: a project may add files
next to its generator copy without that counting as drift.

Exit 0 = clean, no manifest or no package (warnings only), 1 = drift,
2 = usage or environment error. Read-only, standard library only, Python 3.9+.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import List, Optional

MANIFEST = Path("tools") / "manifest.json"


def _looks_like_package(folder: Optional[Path]) -> bool:
    if folder is None or not folder.is_dir():
        return False
    return (folder / "VERSION").is_file() or (folder / MANIFEST).is_file()


def package_dir(root=None) -> Optional[Path]:
    """`<root>/.generator` when it is a Polier package copy, else None.

    Only a project-local copy is checked automatically. The plugin/skill folder
    that runs this file is checked explicitly with `--package` / `package=`.
    """
    if root is None:
        return None
    candidate = Path(root).resolve() / ".generator"
    return candidate if _looks_like_package(candidate) else None


def load_manifest(directory) -> Optional[dict]:
    """Parsed `tools/manifest.json` of `directory`, or None when missing or invalid."""
    try:
        data = json.loads((Path(directory) / MANIFEST).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        return None
    files = {name: digest for name, digest in data["files"].items()
             if isinstance(name, str) and isinstance(digest, str)}
    return {"version": data.get("version") if isinstance(data.get("version"), str) else None,
            "generated": data.get("generated"), "files": files, "count": len(files)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _version(package: Path) -> Optional[str]:
    try:
        return (package / "VERSION").read_text(encoding="utf-8").strip() or None
    except (FileNotFoundError, OSError):
        return None


def _report(package: Optional[Path]) -> dict:
    result = {"package": None, "version": None, "status": "no-package", "files": [], "warnings": []}
    if package is None:
        return result  # no project-local copy: silent, so check.py stays quiet
    package = Path(package)
    result["package"] = str(package)
    if not _looks_like_package(package):
        return result  # not a Polier package: silent, status "no-package"
    result["version"] = _version(package)
    manifest = load_manifest(package)
    if manifest is None:
        result["status"] = "missing-manifest"
        result["warnings"].append(
            f"{package} has no readable tools/manifest.json — reinstall or update Polier once "
            "to get one; drift detection skipped")
        return result

    changed: List[str] = []
    for rel, expected in sorted(manifest["files"].items()):
        path = package / rel
        try:
            current = _sha256(path) if path.is_file() else None
        except OSError:
            current = None
        if current != expected:
            changed.append(rel)
    result["files"] = sorted(changed)
    if result["files"]:
        result["status"] = "modified"
        result["warnings"].append(
            f"{len(result['files'])} file(s) in the generator copy differ from tools/manifest.json — "
            f"local edits or outdated copy: {', '.join(result['files'])}")
    else:
        result["status"] = "ok"
    return result


def drift(root=None, package=None) -> dict:
    """Drift of the project-local copy at `root`, or of `package` when given:
    {package, version, status, files, warnings}, status in
    ok | modified | missing-manifest | no-package. Never raises."""
    if package is not None:
        return _report(Path(package).resolve())
    return _report(package_dir(root))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect local edits or outdated files in the Polier generator copy.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("root", nargs="?", default=".", help="project folder (default: current folder)")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    parser.add_argument("--package", default=None,
                        help="package folder to check explicitly, e.g. the installed plugin/skill copy "
                             "(default: <root>/.generator)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"error: project folder not found: {root}", file=sys.stderr)
        return 2
    if args.package:
        package = Path(args.package).expanduser().resolve()
        if not package.is_dir():
            print(f"error: package folder not found: {package}", file=sys.stderr)
            return 2
        report = drift(root, package=package)
    else:
        report = drift(root)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        if report["package"]:
            print(f"package: {report['package']} (version {report['version'] or 'unknown'})")
        for warning in report["warnings"]:
            print(f"WARN: {warning}")
        if report["status"] == "modified":
            for rel in report["files"]:
                print(f"DRIFT: {rel}")
        elif report["status"] == "ok":
            print(f"DRIFT OK: {report['package']} matches its tools/manifest.json")
        elif report["status"] == "no-package":
            if report["package"]:
                print(f"no package: {report['package']} does not look like a Polier package "
                      "(no VERSION, no tools/manifest.json)")
            else:
                print(f"no package: {root}/.generator not found — drift check skipped")
    return 1 if report["status"] == "modified" else 0


if __name__ == "__main__":
    sys.exit(main())
