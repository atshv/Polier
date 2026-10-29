"""Pages (2.3): the project's Markdown as one browsable knowledge layer.

Polier already writes documentation as Markdown: ``ARCHITECTURE.md``,
``AGENTS.md``, ``docs/`` (architecture, contracts, ADRs, gates, research),
``tasks/*.md`` (briefs), ``reviews/*.md`` and the package READMEs. 2.3 makes
that knowledge browsable: one index with collections, page content, search,
favorites, git history (old revisions) and backlinks (which pages and tasks
refer to a page).

The layer is read-only. Writing stays with the agents through the normal
write guard, and every page is a project file — nothing is copied into the
dashboard.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import runtime as runtime_mod
from .errors import PolierError

MAX_BYTES = 600_000
EXCLUDED_FOLDERS = frozenset({
    ".git", "node_modules", "dist", "build", "coverage", ".turbo", "__pycache__",
    ".changes", "reference", "examples", "reviews/evidence", ".DS_Store",
})
ROOT_FILES = frozenset({
    "README.md", "AGENTS.md", "ARCHITECTURE.md", "STATUS.md", "CHANGELOG.md",
    "HANDOFF.md", "RELEASING.md", "CONTRIBUTING.md", "SECURITY.md",
})
PACKAGE_FILES = frozenset({"README.md", "ARCHITECTURE.md"})
LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#\s+(.+?)\s*$")
FAVORITES = "pages.json"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(timespec="seconds")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _read(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _title(text: str, path: str) -> str:
    for line in text.splitlines():
        match = HEADING.match(line)
        if match:
            return match.group(1)
    return Path(path).stem.replace("-", " ").replace("_", " ")


def _excerpt(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", "|", "```", ">", "-", "*")):
            return stripped[:200]
    return ""


def _candidate(root: Path, relative: str) -> bool:
    """The page paths the viewer may open."""
    if not relative or relative.startswith(("/", ".")) or ".." in Path(relative).parts:
        return False
    path = root / relative
    if not path.is_file() or path.suffix.lower() != ".md":
        return False
    parts = Path(relative).parts
    if any(part in EXCLUDED_FOLDERS for part in parts):
        return False
    if relative in ROOT_FILES and len(parts) == 1:
        return True
    if parts[0] in ("docs", "tasks"):
        return True
    if parts[0] == "reviews":
        return len(parts) == 2
    if parts[0] in ("packages", "services", "apps", "tools", "infra") and len(parts) >= 3:
        return parts[-1] in PACKAGE_FILES
    return False


def _collection(relative: str) -> Dict[str, str]:
    parts = Path(relative).parts
    if len(parts) == 1:
        return {"id": "root", "title": "Project root", "sub": ""}
    top = parts[0]
    if top == "docs":
        sub = parts[1] if len(parts) > 2 else ""
        return {"id": "docs", "title": "Documentation", "sub": sub}
    if top == "tasks":
        return {"id": "tasks", "title": "Task briefs", "sub": ""}
    if top == "reviews":
        return {"id": "reviews", "title": "Reviews", "sub": ""}
    return {"id": "packages", "title": "Package documentation", "sub": parts[1] if len(parts) > 2 else ""}


def _kind(relative: str) -> str:
    parts = Path(relative).parts
    if len(parts) == 1:
        return "root"
    if parts[0] == "docs":
        return "doc"
    if parts[0] == "tasks":
        return "task"
    if parts[0] == "reviews":
        return "review"
    return "package"


def _links(root: Path, relative: str, text: str) -> List[str]:
    base = Path(relative).parent
    found: List[str] = []
    for _label, target in LINK.findall(text):
        if not target or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = target.split("#", 1)[0]
        if not target:
            continue
        candidate = (base / target).as_posix()
        # Normalize "./x", "docs/../docs/y".
        normalized = Path(candidate)
        try:
            candidate = normalized.as_posix()
        except Exception:  # noqa: BLE001
            continue
        if candidate.startswith("./"):
            candidate = candidate[2:]
        if ".." in Path(candidate).parts:
            parts: List[str] = []
            for part in Path(candidate).parts:
                if part == "..":
                    if parts:
                        parts.pop()
                else:
                    parts.append(part)
            candidate = "/".join(parts)
        if _candidate(root, candidate) and candidate not in found:
            found.append(candidate)
    return found


def _page(root: Path, relative: str) -> Optional[Dict[str, Any]]:
    if not _candidate(root, relative):
        return None
    path = root / relative
    text = _read(path)
    if text == "" and path.stat().st_size > MAX_BYTES:
        text = ""
    collection = _collection(relative)
    stat = path.stat()
    return {
        "path": relative,
        "title": _title(text, relative),
        "kind": _kind(relative),
        "collection": collection["id"],
        "collection_title": collection["title"],
        "subcollection": collection["sub"],
        "words": len(text.split()),
        "size": stat.st_size,
        "updated": _iso(stat.st_mtime),
        "excerpt": _excerpt(text),
        "links": _links(root, relative, text),
        "favorite": False,
    }


def collect(root) -> List[Dict[str, Any]]:
    """Every viewable Markdown page, in stable path order."""
    root = Path(root).resolve()
    paths: List[str] = []
    for name in sorted(ROOT_FILES):
        if (root / name).is_file():
            paths.append(name)
    for folder in ("docs", "tasks"):
        base = root / folder
        if base.is_dir():
            for path in sorted(base.rglob("*.md")):
                relative = path.relative_to(root).as_posix()
                if _candidate(root, relative):
                    paths.append(relative)
    reviews = root / "reviews"
    if reviews.is_dir():
        for path in sorted(reviews.glob("*.md")):
            relative = path.relative_to(root).as_posix()
            if _candidate(root, relative):
                paths.append(relative)
    for top in ("packages", "services", "apps", "tools", "infra"):
        base = root / top
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            relative = path.relative_to(root).as_posix()
            if _candidate(root, relative):
                paths.append(relative)
    seen: set = set()
    pages: List[Dict[str, Any]] = []
    for relative in paths:
        if relative in seen:
            continue
        seen.add(relative)
        page = _page(root, relative)
        if page is not None:
            pages.append(page)
    favorites = set(load_favorites(root).get("favorites") or [])
    for page in pages:
        page["favorite"] = page["path"] in favorites
    pages.sort(key=lambda page: (page["collection"], page["subcollection"], page["path"]))
    return pages


def index(root) -> Dict[str, Any]:
    pages = collect(root)
    collections: List[Dict[str, Any]] = []
    seen: Dict[tuple, Dict[str, Any]] = {}
    for page in pages:
        key = (page["collection"], page["collection_title"], page["subcollection"])
        if key not in seen:
            collection_id = page["collection"]
            if page["subcollection"]:
                collection_id = f"{collection_id}/{page['subcollection']}"
            seen[key] = {
                "id": collection_id,
                "title": page["collection_title"],
                "sub": page["subcollection"],
                "pages": [],
            }
            collections.append(seen[key])
        seen[key]["pages"].append({
            "path": page["path"], "title": page["title"], "kind": page["kind"],
            "words": page["words"], "updated": page["updated"],
            "subcollection": page["subcollection"], "favorite": page["favorite"],
        })
    return {"generated_at": _now(), "pages": pages, "collections": collections,
            "counts": {"pages": len(pages), "collections": len(collections),
                       "favorites": len([page for page in pages if page["favorite"]])}}


def page(root, relative: str, ref: Optional[str] = None) -> Dict[str, Any]:
    """One page with content, links, backlinks and (optionally) an old revision."""
    root = Path(root).resolve()
    relative = _text(relative).lstrip("/")
    current = _page(root, relative)
    if current is None:
        raise KeyError(relative)
    text = _read(root / relative)
    if ref:
        text = revision(root, relative, ref)
    result = dict(current)
    result["text"] = text
    result["backlinks"] = backlinks(root, relative)
    result["history"] = history(root, relative)
    result["ref"] = ref
    return result


def revision(root, relative: str, ref: str) -> str:
    root = Path(root).resolve()
    if not _candidate(root, relative):
        raise KeyError(relative)
    if not re.match(r"^[0-9a-fA-F]{7,40}$", ref or ""):
        raise PolierError("ref must be a git commit hash")
    try:
        result = subprocess.run(["git", "-C", str(root), "show", f"{ref}:{relative}"],
                                capture_output=True, text=True, check=False)
    except FileNotFoundError:
        raise PolierError("git is not available")
    if result.returncode != 0:
        raise KeyError(ref)
    return result.stdout


def history(root, relative: str, limit: int = 20) -> List[Dict[str, Any]]:
    root = Path(root).resolve()
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "log", "--follow", "-n", str(max(1, limit)),
             "--date=short", "--format=%h|%ad|%an|%s", "--", relative],
            capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return []
    if result.returncode != 0:
        return []
    commits: List[Dict[str, Any]] = []
    for line in result.stdout.splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            commits.append({"hash": parts[0], "date": parts[1], "author": parts[2],
                            "subject": parts[3]})
    return commits


def _task_backlinks(root: Path, relative: str) -> List[Dict[str, Any]]:
    try:
        board = json.loads((root / "board.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    found: List[Dict[str, Any]] = []
    for task in board.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        references = list(task.get("scope_read") or []) + list(task.get("scope_write") or [])
        for entry in references:
            if not isinstance(entry, str):
                continue
            clean = entry.rstrip("/")
            if relative == clean or relative.startswith(clean + "/"):
                found.append({"id": task.get("id"), "title": task.get("title"),
                              "status": task.get("status"), "kind": "task"})
                break
    return found


def backlinks(root, relative: str) -> List[Dict[str, Any]]:
    root = Path(root).resolve()
    pages = collect(root)
    linked: List[Dict[str, Any]] = []
    for other in pages:
        if other["path"] == relative:
            continue
        if relative in other.get("links") or []:
            linked.append({"path": other["path"], "title": other["title"], "kind": "page"})
    linked.extend(_task_backlinks(root, relative))
    return linked


def search(root, query: str, limit: int = 50) -> List[Dict[str, Any]]:
    root = Path(root).resolve()
    query = _text(query)
    if len(query) < 2:
        return []
    needle = query.casefold()
    results: List[Dict[str, Any]] = []
    for page in collect(root):
        text = _read(root / page["path"])
        title_hit = needle in page["title"].casefold()
        path_hit = needle in page["path"].casefold()
        haystack = text.casefold()
        count = haystack.count(needle)
        if not (title_hit or path_hit or count):
            continue
        position = haystack.find(needle)
        snippet = ""
        if position >= 0:
            start = max(0, position - 60)
            snippet = " ".join(text[start:position + 120].split())
        results.append({**page, "score": (5 if title_hit else 0) + (3 if path_hit else 0)
                        + min(count, 40), "hits": count, "snippet": snippet})
    results.sort(key=lambda item: (-item["score"], item["path"]))
    return results[:max(1, limit)]


def _favorite_path(root: Path) -> Path:
    return runtime_mod.runtime_dir(root) / FAVORITES


def load_favorites(root) -> Dict[str, Any]:
    value = runtime_mod.read_json(_favorite_path(Path(root).resolve()))
    favorites = [entry for entry in value.get("favorites") or [] if isinstance(entry, str)]
    return {"favorites": favorites, "updated": value.get("updated")}


def set_favorites(root, paths: Iterable[str]) -> Dict[str, Any]:
    root = Path(root).resolve()
    clean: List[str] = []
    for path in paths:
        if isinstance(path, str) and _candidate(root, path) and path not in clean:
            clean.append(path)
    value = {"favorites": clean, "updated": _now()}
    runtime_mod.write_json(_favorite_path(root), value)
    return value
