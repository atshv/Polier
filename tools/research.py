#!/usr/bin/env python3
"""Research records for a project: verified versions and cited research notes.

Usage:
    python3 tools/research.py deps     [--root PATH] [--json]
    python3 tools/research.py versions [--root PATH] [--lookup] [--write] [--json]
    python3 tools/research.py note "<topic>" [--root PATH] [--question TEXT]
                                       [--task ID] [--source URL ...]
    python3 tools/research.py check    [--root PATH] [--json]

`deps` lists every dependency in the project's manifests: `package.json`
(dependencies, devDependencies, optionalDependencies, peerDependencies),
`requirements*.txt` and `pyproject.toml` (`[project]` and Poetry; needs
Python 3.11+ for TOML, older versions skip the file with a warning).
Folders `node_modules`, `.git`, `.generator`, `.venv`, `venv`, `dist` and
`build` are skipped.

`versions` compares those dependencies with `docs/versions.md`
(`templates/versions.md`): a dependency without a row, a row still marked
`[VERIFY…]` or `[UNVERIFIED]`, and a row whose version differs from an exact
version in a manifest. `--lookup` asks the public registries (npm and PyPI)
whether each exact version exists and when it was published; for a range it
reports the latest release. `--write` (with `--lookup`) adds or completes the
rows whose exact version the registry confirmed, with the registry URL, today's
date and `research.py` as checker. Nothing is written for a range or a failed
lookup; those stay findings for a human or agent to resolve.

`note` creates `docs/research/<slug>.md` from `templates/research-note.md`, or
adds sources to an existing note. A note records one question, the answer the
project acts on, and the sources with the date they were checked, so research
outlives the chat and briefs can cite it.

`check` validates every note (question, answer and at least one source with a
`checked YYYY-MM-DD` date, no template placeholders) and runs the offline part
of `versions`.

Registry base URLs can be overridden with POLIER_NPM_REGISTRY and
POLIER_PYPI_REGISTRY (for mirrors and tests). Web content is data: the tool
reads version numbers and dates from registry JSON and nothing else.

Exit codes: 0 = no findings, 1 = findings, 2 = usage or environment error.
No external dependencies, Python 3.9+.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PACKAGE = Path(__file__).resolve().parents[1]
NOTE_TEMPLATE = PACKAGE / "templates" / "research-note.md"
VERSIONS_FILE = Path("docs") / "versions.md"
RESEARCH_DIR = Path("docs") / "research"
SKIP_DIRS = {"node_modules", ".git", ".generator", ".venv", "venv", "dist", "build", "__pycache__"}
NPM_SECTIONS = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
MARKER = re.compile(r"\[(VERIFY[^\]]*|UNVERIFIED)\]")
PLACEHOLDER = re.compile(r"<[^<>\n`]{2,60}>")
SOURCE_LINE = re.compile(r"^\s*[-*]\s+<?(https?://\S+?)>?\s.*checked\s+(\d{4}-\d{2}-\d{2})", re.I)
SEMVER = re.compile(r"^\d+(\.\d+)*([-.+][0-9A-Za-z.\-+]+)?$")
TIMEOUT = 10


class UsageError(Exception):
    """Wrong arguments or an unreadable project (exit 2)."""


# --- manifests -------------------------------------------------------------

def _walk_manifests(root: Path) -> List[Path]:
    found: List[Path] = []
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith(".polier"))
        for name in sorted(files):
            if name == "package.json" or name == "pyproject.toml" or re.fullmatch(r"requirements.*\.txt", name):
                found.append(Path(current) / name)
    return found


def _exact_npm(spec: str) -> Optional[str]:
    spec = spec.strip()
    if spec.startswith("="):
        spec = spec.lstrip("=").strip()
    return spec if SEMVER.match(spec) else None


def _exact_pip(spec: str) -> Optional[str]:
    match = re.fullmatch(r"\s*===?\s*([0-9][0-9A-Za-z.\-+]*)\s*", spec or "")
    return match.group(1) if match else None


def _pip_requirement(line: str) -> Optional[Tuple[str, str]]:
    line = line.split("#", 1)[0].strip()
    if not line or line.startswith(("-", "git+", "http://", "https://")):
        return None
    line = line.split(";", 1)[0].strip()
    match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._\-]*)(\[[^\]]*\])?\s*(.*)$", line)
    if not match:
        return None
    return match.group(1), match.group(3).strip()


def _load_toml(path: Path, warnings: List[str]) -> Optional[dict]:
    try:
        import tomllib  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        warnings.append(f"{path}: TOML needs Python 3.11+; file skipped")
        return None
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        warnings.append(f"{path}: cannot parse ({exc})")
        return None


def dependencies(root: Path, warnings: Optional[List[str]] = None) -> List[dict]:
    """Every dependency in the project's manifests, one dict per name and manifest."""
    warnings = warnings if warnings is not None else []
    deps: List[dict] = []
    manifests = _walk_manifests(root)
    internal = _internal_names(manifests)
    for path in manifests:
        rel = path.relative_to(root).as_posix()
        if path.name == "package.json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                warnings.append(f"{rel}: cannot parse ({exc})")
                continue
            for section in NPM_SECTIONS:
                for name, spec in sorted((data.get(section) or {}).items()):
                    if not isinstance(spec, str) or spec.startswith(("workspace:", "file:", "link:", "git", "http")):
                        continue
                    deps.append({"name": name, "spec": spec, "exact": _exact_npm(spec),
                                 "ecosystem": "npm", "manifest": rel})
        elif path.name == "pyproject.toml":
            data = _load_toml(path, warnings)
            if data is None:
                continue
            for line in (data.get("project") or {}).get("dependencies") or []:
                parsed = _pip_requirement(line)
                if parsed:
                    deps.append({"name": parsed[0], "spec": parsed[1], "exact": _exact_pip(parsed[1]),
                                 "ecosystem": "pypi", "manifest": rel})
            poetry = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
            for name, spec in sorted(poetry.items()):
                if name.lower() == "python":
                    continue
                spec = spec.get("version", "") if isinstance(spec, dict) else str(spec)
                exact = spec if SEMVER.match(spec.strip()) else _exact_pip(spec)
                deps.append({"name": name, "spec": spec, "exact": exact, "ecosystem": "pypi", "manifest": rel})
        else:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError as exc:
                warnings.append(f"{rel}: cannot read ({exc})")
                continue
            for line in lines:
                parsed = _pip_requirement(line)
                if parsed:
                    deps.append({"name": parsed[0], "spec": parsed[1], "exact": _exact_pip(parsed[1]),
                                 "ecosystem": "pypi", "manifest": rel})
    return [dep for dep in deps if dep["name"].lower() not in internal]


def _internal_names(manifests: List[Path]) -> set:
    """Names of the project's own packages (workspace members are not looked up)."""
    names = set()
    for path in manifests:
        if path.name != "package.json":
            continue
        try:
            name = json.loads(path.read_text(encoding="utf-8")).get("name")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(name, str) and name:
            names.add(name.lower())
    return names


# --- docs/versions.md ------------------------------------------------------

def _cells(line: str) -> List[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _plain(cell: str) -> str:
    return cell.strip().strip("`").strip()


def read_versions(root: Path) -> Tuple[List[str], Dict[str, dict]]:
    """Lines of docs/versions.md and its table rows by lower-case name."""
    path = root / VERSIONS_FILE
    if not path.is_file():
        return [], {}
    return read_versions_from(path.read_text(encoding="utf-8").splitlines())


def version_findings(root: Path, deps: List[dict]) -> List[str]:
    findings: List[str] = []
    lines, rows = read_versions(root)
    if deps and not lines:
        findings.append(f"{VERSIONS_FILE}: missing; {len(deps)} dependencies have no recorded version "
                        f"(copy templates/versions.md, then run research.py versions --lookup --write)")
        return findings
    for row in _unique_rows(rows):
        if MARKER.search(row["text"]):
            findings.append(f"{VERSIONS_FILE}: `{row['name']}` is still marked {MARKER.search(row['text']).group(0)}")
    seen = set()
    for dep in deps:
        key = dep["name"].lower()
        if key in seen:
            continue
        seen.add(key)
        row = rows.get(key)
        if row is None:
            findings.append(f"{VERSIONS_FILE}: no row for `{dep['name']}` ({dep['manifest']})")
        elif dep["exact"] and row["version"] and not MARKER.search(row["text"]) and row["version"] != dep["exact"]:
            findings.append(f"{VERSIONS_FILE}: `{dep['name']}` is {row['version']} here but {dep['exact']} in {dep['manifest']}")
    return findings


# --- registry lookup -------------------------------------------------------

def _registry(ecosystem: str) -> str:
    if ecosystem == "npm":
        return os.environ.get("POLIER_NPM_REGISTRY", "https://registry.npmjs.org").rstrip("/")
    return os.environ.get("POLIER_PYPI_REGISTRY", "https://pypi.org").rstrip("/")


def _get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "polier-research"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 (fixed registry hosts)
        return json.loads(response.read().decode("utf-8"))


def lookup(dep: dict) -> dict:
    """Ask the registry about one dependency; never raises."""
    base = _registry(dep["ecosystem"])
    name = dep["name"]
    if dep["ecosystem"] == "npm":
        api = f"{base}/{urllib.parse.quote(name, safe='@')}"
        page = f"https://www.npmjs.com/package/{name}"
    else:
        api = f"{base}/pypi/{urllib.parse.quote(name)}/json"
        page = f"https://pypi.org/project/{name}/"
    result = {"name": name, "ecosystem": dep["ecosystem"], "spec": dep["spec"], "exact": dep["exact"],
              "source": page, "ok": False}
    try:
        data = _get_json(api)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        result["error"] = f"lookup failed ({getattr(exc, 'reason', exc)})"
        return result
    if dep["ecosystem"] == "npm":
        latest = (data.get("dist-tags") or {}).get("latest")
        versions = set((data.get("versions") or {}).keys())
        times = data.get("time") or {}
    else:
        latest = (data.get("info") or {}).get("version")
        releases = data.get("releases") or {}
        versions = set(releases.keys())
        times = {v: (files[0].get("upload_time_iso_8601") or files[0].get("upload_time"))
                 for v, files in releases.items() if files}
    result["latest"] = latest
    if dep["exact"]:
        if dep["exact"] in versions:
            result["ok"] = True
            result["version"] = dep["exact"]
            result["published"] = str(times.get(dep["exact"]) or "")[:10]
            if dep["ecosystem"] == "pypi":
                result["source"] = f"https://pypi.org/project/{name}/{dep['exact']}/"
            else:
                result["source"] = f"https://www.npmjs.com/package/{name}/v/{dep['exact']}"
        else:
            result["error"] = f"version {dep['exact']} not found in the registry (latest {latest})"
    else:
        result["error"] = f"range `{dep['spec'] or '*'}` is not an exact version (latest {latest}); pin it"
    return result


def write_rows(root: Path, confirmed: List[dict], today: str) -> int:
    """Add or complete rows for registry-confirmed versions; returns rows changed."""
    path = root / VERSIONS_FILE
    lines, rows = read_versions(root)
    if not lines:
        template = (PACKAGE / "templates" / "versions.md").read_text(encoding="utf-8")
        kept = [line for line in template.splitlines()
                if not (line.startswith("| `<") and line.rstrip().endswith("|"))]
        lines = kept
        path.parent.mkdir(parents=True, exist_ok=True)
        _, rows = read_versions_from(lines)
    changed = 0
    for item in confirmed:
        new = (f"| `{item['name']}` | `{item['version']}` | {item['source']} | {today} | research.py |")
        row = rows.get(item["name"].lower())
        if row is not None:
            if MARKER.search(row["text"]) or row["version"] != item["version"]:
                lines[row["line"]] = new
                changed += 1
            continue
        insert_at = _table_end(lines)
        lines.insert(insert_at, new)
        rows = read_versions_from(lines)[1]
        changed += 1
    if changed:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed


ALIAS_URL = re.compile(r"(?:registry\.npmjs\.org|npmjs\.com/package|pypi\.org/(?:project|pypi))/((?:@[^/\s%]+(?:/|%2[fF]))?[^/\s|]+)")


def read_versions_from(lines: List[str]) -> Tuple[List[str], Dict[str, dict]]:
    """Table rows of a versions file given as lines, keyed by every lower-case alias.

    A row answers to the names in backticks in its first cell, the first cell
    itself, and the package named in a registry URL, so a row titled
    "React DOM (`react-dom`)" or "Next.js" with an npm URL still matches.
    """
    rows: Dict[str, dict] = {}
    has_header = any(line.strip().startswith("|") and _cells(line)[0].lower().startswith("tool") for line in lines)
    in_table = False
    for index, line in enumerate(lines):
        if not line.strip().startswith("|"):
            in_table = False
            continue
        if not has_header:
            in_table = True  # a bare table without the template header still counts
        cells = _cells(line)
        if cells and cells[0].lower().startswith("tool"):
            in_table = True
            continue
        if not in_table or set("".join(cells)) <= set("-: "):
            continue
        first = cells[0]
        name = _plain(first)
        if not name or name.startswith("<"):
            continue
        version_cell = _plain(cells[1]) if len(cells) > 1 else ""
        number = re.match(r"[0-9][0-9A-Za-z.\-+]*", version_cell)
        row = {"name": name, "version": number.group(0) if number else version_cell, "line": index, "text": line}
        aliases = {name.lower()} | {a.lower() for a in re.findall(r"`([^`]+)`", first)}
        for match in ALIAS_URL.finditer(line):
            aliases.add(urllib.parse.unquote(match.group(1)).lower())
        for alias in aliases:
            rows.setdefault(alias, row)
    return lines, rows


def _unique_rows(rows: Dict[str, dict]) -> List[dict]:
    seen: Dict[int, dict] = {}
    for row in rows.values():
        seen.setdefault(row["line"], row)
    return [seen[k] for k in sorted(seen)]


def _table_end(lines: List[str]) -> int:
    in_table = False
    last = None
    for index, line in enumerate(lines):
        if line.strip().startswith("|") and _cells(line)[0].lower().startswith("tool"):
            in_table = True
        if in_table:
            if line.strip().startswith("|"):
                last = index
            else:
                break
    return (last + 1) if last is not None else len(lines)


# --- research notes --------------------------------------------------------

def slugify(topic: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    return slug[:60].rstrip("-") or "note"


def create_note(root: Path, topic: str, question: str = "", task: str = "",
                sources: Optional[List[str]] = None, today: Optional[str] = None) -> Tuple[Path, bool]:
    today = today or dt.date.today().isoformat()
    sources = sources or []
    for url in sources:
        if not re.match(r"^https?://", url):
            raise UsageError(f"--source must be an http(s) URL, got {url!r}")
    path = root / RESEARCH_DIR / f"{slugify(topic)}.md"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        added = [f"- {url} (checked {today}) — <what it confirms>" for url in sources if url not in text]
        if added:
            marker = "## Sources"
            if marker in text:
                head, tail = text.split(marker, 1)
                body = tail.lstrip("\n")
                text = f"{head}{marker}\n\n" + "\n".join(added) + "\n" + body
            else:
                text = text.rstrip() + f"\n\n{marker}\n\n" + "\n".join(added) + "\n"
            path.write_text(text, encoding="utf-8")
        return path, False
    template = NOTE_TEMPLATE.read_text(encoding="utf-8")
    text = (template.replace("<topic>", topic).replace("<slug>", slugify(topic))
            .replace("YYYY-MM-DD", today))
    if question:
        text = text.replace("<the question, one sentence>", question)
    if task:
        text = text.replace("<task ID or phase>", task)
    if sources:
        lines = "\n".join(f"- {url} (checked {today}) — <what it confirms>" for url in sources)
        text = re.sub(r"^- <URL> \(checked [^)]*\) — <what it confirms>$", lambda _m: lines, text, count=1, flags=re.M)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path, True


def note_findings(root: Path) -> List[str]:
    findings: List[str] = []
    folder = root / RESEARCH_DIR
    if not folder.is_dir():
        return findings
    for path in sorted(folder.glob("*.md")):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        if not re.search(r"^\*\*Question:\*\*\s*\S", text, re.M) or "<the question" in text:
            findings.append(f"{rel}: no question")
        answer = re.search(r"^## Answer\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        if not answer or not answer.group(1).strip() or "<3–10 lines" in answer.group(1):
            findings.append(f"{rel}: no answer")
        sources = [m for m in (SOURCE_LINE.match(line) for line in text.splitlines()) if m]
        if not sources:
            findings.append(f"{rel}: no source with `(checked YYYY-MM-DD)`")
        leftovers = sorted(set(PLACEHOLDER.findall(text)) - {"<URL>"})
        if leftovers:
            findings.append(f"{rel}: template placeholders left: {', '.join(leftovers[:3])}")
    return findings


# --- command line ----------------------------------------------------------

def _print(findings: List[str], warnings: List[str], ok_message: str) -> None:
    for warning in warnings:
        print(f"WARN: {warning}")
    for finding in findings:
        print(f"FINDING: {finding}")
    if not findings:
        print(ok_message)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("deps", "versions", "check"):
        p = sub.add_parser(name)
        p.add_argument("--root", default=".")
        p.add_argument("--json", action="store_true")
        if name == "versions":
            p.add_argument("--lookup", action="store_true", help="ask npm/PyPI about every dependency")
            p.add_argument("--write", action="store_true", help="with --lookup: record confirmed versions")
    p = sub.add_parser("note")
    p.add_argument("topic")
    p.add_argument("--root", default=".")
    p.add_argument("--question", default="")
    p.add_argument("--task", default="")
    p.add_argument("--source", action="append", default=[])
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"error: {root} is not a folder", file=sys.stderr)
        return 2
    warnings: List[str] = []
    try:
        if args.command == "note":
            path, created = create_note(root, args.topic, args.question, args.task, args.source)
            print(f"{'created' if created else 'updated'}: {path.relative_to(root).as_posix()}")
            return 0

        deps = dependencies(root, warnings)
        if args.command == "deps":
            if args.json:
                print(json.dumps({"dependencies": deps, "warnings": warnings}, indent=2))
            else:
                for warning in warnings:
                    print(f"WARN: {warning}")
                for dep in deps:
                    print(f"{dep['ecosystem']:5} {dep['name']} {dep['spec'] or '*'}  ({dep['manifest']})")
                print(f"{len(deps)} dependencies")
            return 0

        if args.command == "versions":
            if args.write and not args.lookup:
                raise UsageError("--write needs --lookup")
            results: List[dict] = []
            written = 0
            if args.lookup:
                unique = {(d["ecosystem"], d["name"].lower()): d for d in deps}
                results = [lookup(d) for d in unique.values()]
                if args.write:
                    written = write_rows(root, [r for r in results if r["ok"]], dt.date.today().isoformat())
            findings = version_findings(root, deps)
            findings += [f"{r['name']}: {r['error']}" for r in results if not r["ok"]]
            if args.json:
                print(json.dumps({"findings": findings, "lookups": results, "written": written,
                                  "warnings": warnings}, indent=2))
            else:
                for r in results:
                    if r["ok"]:
                        print(f"OK: {r['name']} {r['version']} (published {r['published'] or '?'}, latest {r['latest']})")
                if args.write:
                    print(f"written: {written} row(s) in {VERSIONS_FILE}")
                _print(findings, warnings, "versions: every dependency is recorded")
            return 1 if findings else 0

        findings = note_findings(root) + version_findings(root, deps)
        if args.json:
            print(json.dumps({"findings": findings, "warnings": warnings}, indent=2))
        else:
            _print(findings, warnings, "research: notes and versions complete")
        return 1 if findings else 0
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
