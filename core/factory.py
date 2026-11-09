"""The software factory line: stations, checklist items and their evidence.

A project built with Polier moves through nine stations — idea, concept,
design, architecture, plan, build, verify, release, operate. The package's
``factory/catalog.json`` lists every checklist item a piece of software can
need (web, iOS, Android, desktop, CLI, service) and when it applies. The
project's ``factory.json`` records which platforms and traits it has, the
items that apply, their status and their evidence, and the station each
step of the line is at. Only ``tools/factory.py`` writes it.

Rules, the same for every harness:

- An item is ``open``, ``done``, ``deferred`` (``should`` items only, with a
  reason) or ``na`` (not applicable, with a reason).
- ``done`` needs evidence: a project path that exists (``docs/concept.md``,
  optionally with a heading anchor ``#personas``) or, for items whose catalog
  evidence is ``task``, linked board tasks that are all ``done``.
- A station closes only when every item of it is resolved and valid, every
  earlier station is closed, and an owner name is given. At the plan station
  every open build and verify item must be linked to a board task.
- Stations without an applicable item close on their own when the line
  reaches them.

Standard library only.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .errors import PolierError

PACKAGE = Path(__file__).resolve().parent.parent
CATALOG = PACKAGE / "factory" / "catalog.json"
FILE = "factory.json"
VERSION = "3.0"

ITEM_STATUSES = ("open", "done", "deferred", "na")
STATION_STATUSES = ("pending", "active", "done")
RESOLVED = ("done", "deferred", "na")


# -- catalog ----------------------------------------------------------------

_catalog_cache: Optional[Dict[str, Any]] = None


def load_catalog(path: Optional[Path] = None) -> Dict[str, Any]:
    """The package catalog: platforms, traits, implications, stations, items."""
    global _catalog_cache
    if path is None and _catalog_cache is not None:
        return _catalog_cache
    source = Path(path) if path else CATALOG
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PolierError(f"cannot read the factory catalog {source}: {exc}")
    if path is None:
        _catalog_cache = data
    return data


def catalog_errors(catalog: Dict[str, Any]) -> List[str]:
    """Structural problems of a catalog (used by the package tests)."""
    errors: List[str] = []
    stations = [s.get("id") for s in catalog.get("stations") or []]
    platforms = set(catalog.get("platforms") or {})
    traits = set(catalog.get("traits") or {})
    seen = set()
    for item in catalog.get("items") or []:
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            errors.append(f"item without id: {item}")
            continue
        if item_id in seen:
            errors.append(f"{item_id}: duplicate id")
        seen.add(item_id)
        if item.get("station") not in stations:
            errors.append(f"{item_id}: unknown station {item.get('station')!r}")
        if item.get("level") not in ("must", "should"):
            errors.append(f"{item_id}: level must be must or should")
        for key in ("title", "detail", "evidence"):
            if not isinstance(item.get(key), str) or not item.get(key).strip():
                errors.append(f"{item_id}: {key} is missing")
        for value in item.get("platforms") or []:
            if value not in platforms:
                errors.append(f"{item_id}: unknown platform {value!r}")
        for value in item.get("traits") or []:
            if value not in traits:
                errors.append(f"{item_id}: unknown trait {value!r}")
    for key, implied in (catalog.get("implies") or {}).items():
        source = key.split(":", 1)
        if source[0] == "platform":
            if source[1] not in platforms:
                errors.append(f"implies: unknown platform {source[1]!r}")
        elif key not in traits:
            errors.append(f"implies: unknown trait {key!r}")
        for value in implied:
            if value not in traits:
                errors.append(f"implies {key}: unknown trait {value!r}")
    return errors


def station_ids(catalog: Optional[Dict[str, Any]] = None) -> List[str]:
    catalog = catalog or load_catalog()
    return [station["id"] for station in catalog["stations"]]


def station_info(station_id: str, catalog: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    catalog = catalog or load_catalog()
    for station in catalog["stations"]:
        if station["id"] == station_id:
            return station
    raise PolierError(f"unknown station {station_id!r}; stations: {', '.join(station_ids(catalog))}")


def catalog_item(item_id: str, catalog: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    catalog = catalog or load_catalog()
    wanted = item_id.strip().upper()
    for item in catalog["items"]:
        if item["id"] == wanted:
            return item
    raise PolierError(f"unknown factory item {item_id!r}")


def resolve_traits(platforms: Iterable[str], traits: Iterable[str],
                   catalog: Optional[Dict[str, Any]] = None) -> List[str]:
    """The declared traits plus everything the platforms and traits imply."""
    catalog = catalog or load_catalog()
    implies = catalog.get("implies") or {}
    result = set(traits)
    for platform in platforms:
        result.update(implies.get(f"platform:{platform}", []))
    changed = True
    while changed:
        changed = False
        for trait in list(result):
            for implied in implies.get(trait, []):
                if implied not in result:
                    result.add(implied)
                    changed = True
    return sorted(result)


def applies(item: Dict[str, Any], platforms: Iterable[str], traits: Iterable[str]) -> bool:
    """An item applies when one of its platforms and one of its traits match."""
    platforms, traits = set(platforms), set(traits)
    wanted_platforms = item.get("platforms") or []
    wanted_traits = item.get("traits") or []
    if wanted_platforms and not platforms.intersection(wanted_platforms):
        return False
    if wanted_traits and not traits.intersection(wanted_traits):
        return False
    return True


def applicable_items(platforms: Iterable[str], traits: Iterable[str],
                     catalog: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    catalog = catalog or load_catalog()
    platforms, traits = list(platforms), list(traits)
    return [item for item in catalog["items"] if applies(item, platforms, traits)]


def validate_scope(platforms: List[str], traits: List[str],
                   catalog: Optional[Dict[str, Any]] = None) -> None:
    catalog = catalog or load_catalog()
    if not platforms:
        raise PolierError("name at least one platform: " + ", ".join(catalog["platforms"]))
    unknown = [p for p in platforms if p not in catalog["platforms"]]
    if unknown:
        raise PolierError(f"unknown platform(s) {', '.join(unknown)}; known: {', '.join(catalog['platforms'])}")
    unknown = [t for t in traits if t not in catalog["traits"]]
    if unknown:
        raise PolierError(f"unknown trait(s) {', '.join(unknown)}; known: {', '.join(catalog['traits'])}")


# -- project file -----------------------------------------------------------

def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def path_of(root) -> Path:
    return Path(root) / FILE


def load(root) -> Optional[Dict[str, Any]]:
    """factory.json of a project, or None when the project has none."""
    path = path_of(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise PolierError(f"{FILE} is not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise PolierError(f"{FILE} must hold a JSON object")
    return data


def need(root) -> Dict[str, Any]:
    data = load(root)
    if data is None:
        raise PolierError(f"no {FILE} in {root}; start the line with: tools/factory.py init --platforms <list>")
    return data


def save(root, data: Dict[str, Any]) -> Path:
    """Atomic write of factory.json (2-space JSON, trailing newline)."""
    path = path_of(root)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=".factory.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def _event(data: Dict[str, Any], kind: str, by: Optional[str] = None, **fields: Any) -> None:
    entry: Dict[str, Any] = {"at": _now(), "event": kind}
    if by:
        entry["by"] = by
    entry.update({key: value for key, value in fields.items() if value not in (None, "", [])})
    data.setdefault("history", []).append(entry)


def preview(platforms: List[str], traits: List[str]) -> Dict[str, Any]:
    """What init would write: the scope and the item count per station, without writing."""
    catalog = load_catalog()
    platforms = sorted(dict.fromkeys(p.strip().lower() for p in platforms if p.strip()))
    declared = sorted(dict.fromkeys(t.strip().lower() for t in traits if t.strip()))
    validate_scope(platforms, declared, catalog)
    resolved = resolve_traits(platforms, declared, catalog)
    items = applicable_items(platforms, resolved, catalog)
    return {
        "platforms": platforms,
        "traits": resolved,
        "items": len(items),
        "stations": {sid: sum(1 for item in items if item["station"] == sid) for sid in station_ids(catalog)},
    }


def init(root, platforms: List[str], traits: List[str], by: Optional[str] = None,
         force: bool = False) -> Dict[str, Any]:
    """Create factory.json: scope, applicable items (all open), first station active."""
    catalog = load_catalog()
    platforms = sorted(dict.fromkeys(p.strip().lower() for p in platforms if p.strip()))
    declared = sorted(dict.fromkeys(t.strip().lower() for t in traits if t.strip()))
    validate_scope(platforms, declared, catalog)
    if path_of(root).exists() and not force:
        raise PolierError(f"{FILE} exists; change the scope with: tools/factory.py scope --platforms … --traits …")
    resolved = resolve_traits(platforms, declared, catalog)
    data: Dict[str, Any] = {
        "factory_version": VERSION,
        "platforms": platforms,
        "traits": declared,
        "resolved_traits": resolved,
        "stations": {sid: {"status": "pending"} for sid in station_ids(catalog)},
        "items": {item["id"]: {"status": "open"} for item in applicable_items(platforms, resolved, catalog)},
        "history": [],
    }
    first = station_ids(catalog)[0]
    data["stations"][first] = {"status": "active", "started": _now()}
    _event(data, "init", by, platforms=platforms, traits=declared)
    save(root, data)
    return data


def rescope(root, platforms: Optional[List[str]] = None, traits: Optional[List[str]] = None,
            by: Optional[str] = None) -> Dict[str, Any]:
    """Change platforms/traits: new items open, items that no longer apply become n/a."""
    catalog = load_catalog()
    data = need(root)
    new_platforms = sorted(dict.fromkeys(p.strip().lower() for p in (platforms if platforms is not None
                                                                       else data.get("platforms", [])) if p.strip()))
    new_traits = sorted(dict.fromkeys(t.strip().lower() for t in (traits if traits is not None
                                                                   else data.get("traits", [])) if t.strip()))
    validate_scope(new_platforms, new_traits, catalog)
    resolved = resolve_traits(new_platforms, new_traits, catalog)
    wanted = {item["id"] for item in applicable_items(new_platforms, resolved, catalog)}
    items = data.setdefault("items", {})
    added, dropped = [], []
    for item_id in sorted(wanted):
        entry = items.get(item_id)
        if entry is None:
            items[item_id] = {"status": "open"}
            added.append(item_id)
        elif entry.get("status") == "na" and entry.get("reason") == "out of scope after a scope change":
            items[item_id] = {"status": "open"}
            added.append(item_id)
    for item_id, entry in items.items():
        if item_id not in wanted and entry.get("status") in ("open", "deferred"):
            items[item_id] = {"status": "na", "reason": "out of scope after a scope change"}
            dropped.append(item_id)
    data["platforms"], data["traits"], data["resolved_traits"] = new_platforms, new_traits, resolved
    _event(data, "scope", by, platforms=new_platforms, traits=new_traits, added=added, dropped=dropped)
    save(root, data)
    return {"added": added, "dropped": dropped, "platforms": new_platforms, "traits": resolved}


# -- evidence ---------------------------------------------------------------

def _slug(text: str) -> str:
    text = re.sub(r"[`*_~\[\]()]", "", text.strip().lower())
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s]+", "-", text).strip("-")


def _headings(path: Path) -> List[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return [_slug(m.group(1)) for m in re.finditer(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, re.MULTILINE)]


def evidence_problem(root, evidence: str) -> Optional[str]:
    """Why one evidence entry does not hold, or None when it does."""
    value = evidence.strip()
    if not value:
        return "empty evidence entry"
    if value.startswith("task:"):
        return None  # checked with the board in item_problems
    rel, _, anchor = value.partition("#")
    rel = rel.strip()
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        return f"evidence {value!r} must be a path inside the project"
    path = Path(root) / rel
    if not path.exists():
        return f"evidence {rel} does not exist"
    if path.is_dir() and not any(path.iterdir()):
        return f"evidence folder {rel} is empty"
    if anchor:
        if not path.is_file():
            return f"evidence {value!r}: an anchor needs a Markdown file"
        if _slug(anchor) not in _headings(path):
            return f"evidence {value!r}: no heading '{anchor}' in {rel}"
    return None


def _board_tasks(root) -> Dict[str, Dict[str, Any]]:
    try:
        data = json.loads((Path(root) / "board.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    tasks = data.get("tasks") if isinstance(data, dict) else None
    return {task["id"]: task for task in tasks or [] if isinstance(task, dict) and isinstance(task.get("id"), str)}


def linked_tasks(entry: Dict[str, Any]) -> List[str]:
    tasks = [t for t in entry.get("tasks") or [] if isinstance(t, str)]
    tasks += [e[5:].strip() for e in entry.get("evidence") or [] if isinstance(e, str) and e.startswith("task:")]
    return list(dict.fromkeys(tasks))


def item_problems(root, item_id: str, entry: Dict[str, Any], board: Optional[Dict[str, Dict[str, Any]]] = None,
                  catalog: Optional[Dict[str, Any]] = None) -> List[str]:
    """Why an item's recorded state does not hold (empty when it does)."""
    catalog = catalog or load_catalog()
    try:
        item = catalog_item(item_id, catalog)
    except PolierError:
        return [f"{item_id}: not in the catalog"]
    board = _board_tasks(root) if board is None else board
    status = entry.get("status")
    problems: List[str] = []
    if status not in ITEM_STATUSES:
        return [f"{item_id}: unknown status {status!r}"]
    for task_id in linked_tasks(entry):
        if task_id not in board:
            problems.append(f"{item_id}: linked task {task_id} is not on the board")
    if status in ("na", "deferred") and not str(entry.get("reason") or "").strip():
        problems.append(f"{item_id}: {status} needs a reason")
    if status == "deferred" and item["level"] == "must":
        problems.append(f"{item_id}: a must item cannot be deferred; do it or mark it n/a with a reason")
    if status == "done":
        tasks = linked_tasks(entry)
        paths = [e for e in entry.get("evidence") or [] if isinstance(e, str) and not e.startswith("task:")]
        if item["evidence"] == "task" and not tasks:
            problems.append(f"{item_id}: done needs at least one linked task (factory.py link {item_id} --task <ID>)")
        if item["evidence"] != "task" and not paths and not tasks:
            problems.append(f"{item_id}: done needs evidence, e.g. --evidence {item['evidence']}")
        for task_id in tasks:
            task = board.get(task_id)
            if task is not None and task.get("status") != "done":
                problems.append(f"{item_id}: linked task {task_id} is {task.get('status')}, not done")
        for value in paths:
            problem = evidence_problem(root, value)
            if problem:
                problems.append(f"{item_id}: {problem}")
    return problems


# -- writes -----------------------------------------------------------------

def set_item(root, item_id: str, status: str, evidence: Optional[List[str]] = None,
             reason: Optional[str] = None, by: Optional[str] = None) -> Dict[str, Any]:
    """Record an item's status; refuses a state that would not hold."""
    catalog = load_catalog()
    data = need(root)
    item = catalog_item(item_id, catalog)
    item_id = item["id"]
    items = data.setdefault("items", {})
    if item_id not in items:
        raise PolierError(f"{item_id} does not apply to this project (platforms/traits); change the scope first")
    if status not in ITEM_STATUSES:
        raise PolierError(f"status must be one of {', '.join(ITEM_STATUSES)}")
    old = dict(items[item_id])
    entry: Dict[str, Any] = {"status": status}
    if old.get("tasks"):
        entry["tasks"] = old["tasks"]
    if status == "done":
        values = [e.strip() for e in (evidence or []) if e and e.strip()]
        if not values:
            values = [e for e in old.get("evidence") or []]
        if values:
            entry["evidence"] = values
    if status in ("na", "deferred"):
        entry["reason"] = (reason or "").strip()
    elif reason:
        entry["note"] = reason.strip()
    problems = item_problems(root, item_id, entry, catalog=catalog)
    if problems:
        raise PolierError("; ".join(problems))
    if status == "done":
        entry["at"] = _now()
        if by:
            entry["by"] = by
    items[item_id] = entry
    _event(data, "item", by, item=item_id, status=status, evidence=entry.get("evidence"),
           reason=entry.get("reason"))
    save(root, data)
    return entry


def link(root, item_id: str, tasks: List[str], by: Optional[str] = None, replace: bool = False) -> Dict[str, Any]:
    """Link board tasks to an item (planning: which task delivers it)."""
    catalog = load_catalog()
    data = need(root)
    item = catalog_item(item_id, catalog)
    item_id = item["id"]
    items = data.setdefault("items", {})
    if item_id not in items:
        raise PolierError(f"{item_id} does not apply to this project (platforms/traits)")
    wanted = [t.strip().upper() for t in tasks if t and t.strip()]
    if not wanted:
        raise PolierError("name at least one task")
    board = _board_tasks(root)
    missing = [t for t in wanted if t not in board]
    if missing:
        raise PolierError(f"not on the board: {', '.join(missing)}")
    entry = items[item_id]
    current = [] if replace else [t for t in entry.get("tasks") or []]
    entry["tasks"] = list(dict.fromkeys(current + wanted))
    _event(data, "link", by, item=item_id, tasks=entry["tasks"])
    save(root, data)
    return entry


# -- evaluation -------------------------------------------------------------

def _station_items(data: Dict[str, Any], station: str, catalog: Dict[str, Any]) -> List[str]:
    order = [item["id"] for item in catalog["items"] if item["station"] == station]
    return [item_id for item_id in order if item_id in (data.get("items") or {})]


def unmapped(data: Dict[str, Any], catalog: Optional[Dict[str, Any]] = None) -> List[str]:
    """Open build/verify items whose catalog evidence is a task and that have no linked task."""
    catalog = catalog or load_catalog()
    result = []
    for item in catalog["items"]:
        entry = (data.get("items") or {}).get(item["id"])
        if entry is None or item["evidence"] != "task" or item["station"] not in ("build", "verify"):
            continue
        if entry.get("status") == "open" and not linked_tasks(entry):
            result.append(item["id"])
    return result


def station_blockers(root, data: Dict[str, Any], station: str,
                     catalog: Optional[Dict[str, Any]] = None,
                     board: Optional[Dict[str, Dict[str, Any]]] = None) -> List[str]:
    """What keeps a station from closing."""
    catalog = catalog or load_catalog()
    board = _board_tasks(root) if board is None else board
    blockers: List[str] = []
    order = station_ids(catalog)
    for earlier in order[:order.index(station)]:
        if (data.get("stations") or {}).get(earlier, {}).get("status") != "done":
            blockers.append(f"station {earlier} is not closed")
    for item_id in _station_items(data, station, catalog):
        entry = data["items"][item_id]
        if entry.get("status") == "open":
            blockers.append(f"{item_id} is open")
        blockers.extend(item_problems(root, item_id, entry, board, catalog))
    if station == "plan":
        missing = unmapped(data, catalog)
        if missing:
            blockers.append("build/verify items without a task: " + ", ".join(missing))
    return blockers


def current_station(data: Dict[str, Any], catalog: Optional[Dict[str, Any]] = None) -> Optional[str]:
    catalog = catalog or load_catalog()
    stations = data.get("stations") or {}
    for station in station_ids(catalog):
        if stations.get(station, {}).get("status") != "done":
            return station
    return None


def evaluate(root, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Read-only report: stations with counts, the current station, errors, warnings."""
    catalog = load_catalog()
    data = data if data is not None else need(root)
    board = _board_tasks(root)
    errors: List[str] = []
    warnings: List[str] = []
    if data.get("factory_version") != VERSION:
        warnings.append(f"factory_version {data.get('factory_version')!r} differs from {VERSION}")
    try:
        validate_scope(list(data.get("platforms") or []), list(data.get("traits") or []), catalog)
    except PolierError as exc:
        errors.append(str(exc))
    resolved = resolve_traits(data.get("platforms") or [], data.get("traits") or [], catalog)
    wanted = {item["id"] for item in applicable_items(data.get("platforms") or [], resolved, catalog)}
    items = data.get("items") or {}
    missing = sorted(wanted - set(items))
    if missing:
        warnings.append("items that apply but are not in factory.json (run factory.py scope): " + ", ".join(missing))
    stations_state = data.get("stations") or {}
    order = station_ids(catalog)
    seen_open = False
    for station in order:
        status = stations_state.get(station, {}).get("status")
        if status not in STATION_STATUSES:
            errors.append(f"station {station}: unknown status {status!r}")
        if status == "done" and seen_open:
            errors.append(f"station {station} is closed while an earlier station is open")
        if status != "done":
            seen_open = True
    report_stations = []
    for station in order:
        info = station_info(station, catalog)
        ids = _station_items(data, station, catalog)
        counts = {key: 0 for key in ITEM_STATUSES}
        invalid = 0
        for item_id in ids:
            entry = items[item_id]
            counts[entry.get("status") if entry.get("status") in counts else "open"] += 1
            problems = item_problems(root, item_id, entry, board, catalog)
            if problems:
                invalid += 1
                target = errors if entry.get("status") in RESOLVED else warnings
                target.extend(problems)
        report_stations.append({
            "id": station, "title": info["title"], "role": info["role"],
            "status": stations_state.get(station, {}).get("status", "pending"),
            "items": len(ids), "invalid": invalid, **counts,
        })
    current = current_station(data, catalog)
    if current and order.index(current) >= order.index("build"):
        gaps = unmapped(data, catalog)
        if gaps:
            errors.append("build/verify items without a task after the plan station: " + ", ".join(gaps))
    if current and order.index(current) < order.index("build"):
        started = [tid for tid, task in board.items()
                   if task.get("status") not in (None, "pending", "claimed")]
        if started:
            warnings.append(f"tasks started before the plan station closed: {', '.join(sorted(started))}")
    resolved_count = sum(1 for e in items.values() if e.get("status") in RESOLVED)
    return {
        "platforms": data.get("platforms") or [],
        "traits": resolved,
        "current": current,
        "stations": report_stations,
        "items_total": len(items),
        "items_resolved": resolved_count,
        "errors": errors,
        "warnings": warnings,
    }


def advance(root, by: str, note: Optional[str] = None) -> Dict[str, Any]:
    """Close the current station (owner decision) and open the next one."""
    if not by or not by.strip():
        raise PolierError("advance needs the owner who approves the station: --by <name>")
    catalog = load_catalog()
    data = need(root)
    current = current_station(data, catalog)
    if current is None:
        raise PolierError("every station is closed; the line is complete")
    blockers = station_blockers(root, data, current, catalog)
    if blockers:
        raise PolierError(f"station {current} cannot close:\n- " + "\n- ".join(blockers))
    closed = [current]
    stations = data.setdefault("stations", {})
    stations[current] = {**stations.get(current, {}), "status": "done", "closed": _now(), "approved_by": by.strip()}
    if note:
        stations[current]["note"] = note.strip()
    _event(data, "advance", by.strip(), station=current, note=note)
    order = station_ids(catalog)
    following = order[order.index(current) + 1:]
    opened = None
    for station in following:
        if _station_items(data, station, catalog):
            stations[station] = {"status": "active", "started": _now()}
            opened = station
            break
        stations[station] = {"status": "done", "closed": _now(), "approved_by": "auto",
                             "note": "no applicable items"}
        closed.append(station)
        _event(data, "skip", "auto", station=station)
    save(root, data)
    return {"closed": closed, "opened": opened}


def next_items(root, data: Optional[Dict[str, Any]] = None, limit: int = 0) -> Dict[str, Any]:
    """The open items of the current station with their catalog text."""
    catalog = load_catalog()
    data = data if data is not None else need(root)
    current = current_station(data, catalog)
    if current is None:
        return {"station": None, "items": []}
    result = []
    for item_id in _station_items(data, current, catalog):
        entry = data["items"][item_id]
        if entry.get("status") != "open":
            continue
        item = catalog_item(item_id, catalog)
        result.append({"id": item_id, "level": item["level"], "title": item["title"],
                       "detail": item["detail"], "evidence": item["evidence"],
                       "tasks": linked_tasks(entry)})
    if limit > 0:
        result = result[:limit]
    info = station_info(current, catalog)
    return {"station": current, "title": info["title"], "role": info["role"], "goal": info["goal"],
            "outputs": info["outputs"], "items": result}


# -- rendering --------------------------------------------------------------

STATUS_MARK = {"open": "[ ]", "done": "[x]", "deferred": "[~]", "na": "[-]"}


def status_line(root, data: Optional[Dict[str, Any]] = None) -> str:
    """One line for STATUS.md: every station with its progress."""
    catalog = load_catalog()
    data = data if data is not None else load(root)
    if data is None:
        return ""
    items = data.get("items") or {}
    current = current_station(data, catalog)
    parts = []
    for station in station_ids(catalog):
        ids = _station_items(data, station, catalog)
        state = (data.get("stations") or {}).get(station, {}).get("status")
        if state == "done":
            parts.append(f"{station} ✓")
        elif station == current:
            done = sum(1 for i in ids if items[i].get("status") in RESOLVED)
            parts.append(f"**{station} {done}/{len(ids)}**")
        else:
            parts.append(station)
    return "Factory: " + " · ".join(parts)


def render_markdown(root, data: Optional[Dict[str, Any]] = None) -> str:
    """docs/factory.md: the project's checklist, generated from factory.json."""
    catalog = load_catalog()
    data = data if data is not None else need(root)
    report = evaluate(root, data)
    items = data.get("items") or {}
    lines = [
        "# Factory checklist",
        "",
        "> Generated by `tools/factory.py render` from `factory.json`. Do not edit by hand.",
        "",
        f"Platforms: {', '.join(report['platforms'])} · Traits: {', '.join(report['traits']) or '—'}",
        f"Current station: **{report['current'] or 'complete'}** · "
        f"{report['items_resolved']}/{report['items_total']} items resolved",
        "",
        "Legend: [x] done · [ ] open · [~] deferred · [-] not applicable",
        "",
    ]
    for station in report["stations"]:
        ids = _station_items(data, station["id"], catalog)
        state = {"done": "closed", "active": "active", "pending": "pending"}.get(station["status"], station["status"])
        lines.append(f"## {station['title']} — {state} ({station['role']})")
        lines.append("")
        if not ids:
            lines.append("No applicable items.")
            lines.append("")
            continue
        for item_id in ids:
            item = catalog_item(item_id, catalog)
            entry = items[item_id]
            mark = STATUS_MARK.get(entry.get("status"), "[?]")
            tail = []
            tasks = linked_tasks(entry)
            if tasks:
                tail.append("tasks " + ", ".join(tasks))
            paths = [e for e in entry.get("evidence") or [] if not str(e).startswith("task:")]
            if paths:
                tail.append("evidence " + ", ".join(f"`{p}`" for p in paths))
            if entry.get("reason"):
                tail.append("reason: " + entry["reason"])
            level = "" if item["level"] == "must" else " *(should)*"
            suffix = f" — {'; '.join(tail)}" if tail else ""
            lines.append(f"- {mark} **{item_id}** {item['title']}{level}{suffix}")
        lines.append("")
    if report["errors"] or report["warnings"]:
        lines.append("## Findings")
        lines.append("")
        lines += [f"- error: {e}" for e in report["errors"]]
        lines += [f"- warning: {w}" for w in report["warnings"]]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def catalog_markdown(platforms: Optional[List[str]] = None, traits: Optional[List[str]] = None) -> str:
    """The catalog as Markdown, optionally filtered to a scope."""
    catalog = load_catalog()
    filtered = platforms is not None
    resolved = resolve_traits(platforms or [], traits or [], catalog) if filtered else []
    lines = ["# Factory catalog", ""]
    if filtered:
        lines += [f"Scope: platforms {', '.join(platforms)} · traits {', '.join(resolved) or '—'}", ""]
    else:
        lines += [
            "> Generated by `tools/factory.py catalog --write`. The source is `factory/catalog.json`.",
            "",
            "Every item applies when one of its platforms **and** one of its traits match the project "
            "(an empty list matches everything). `must` items are done or not applicable; `should` items "
            "may be deferred with a reason. Evidence `task` means a linked board task that is done.",
            "",
            "## Platforms",
            "",
        ]
        lines += [f"- `{key}` — {value}" for key, value in catalog["platforms"].items()]
        lines += ["", "## Traits", ""]
        lines += [f"- `{key}` — {value}" for key, value in catalog["traits"].items()]
        lines += ["", "Implied: " + "; ".join(f"`{k}` → {', '.join(v)}" for k, v in catalog["implies"].items()), ""]
    for station in catalog["stations"]:
        rows = [item for item in catalog["items"] if item["station"] == station["id"]
                and (not filtered or applies(item, platforms, resolved))]
        lines += [f"## {station['title']} — {station['role']}", "", station["goal"], "",
                  "Outputs: " + ", ".join(f"`{o}`" for o in station["outputs"]), ""]
        if not rows:
            lines += ["No applicable items.", ""]
            continue
        lines += ["| ID | Level | Item | Applies to | Evidence |", "| --- | --- | --- | --- | --- |"]
        for item in rows:
            scope = ", ".join((item.get("platforms") or []) + (item.get("traits") or [])) or "all"
            lines.append(f"| {item['id']} | {item['level']} | **{item['title']}** — {item['detail']} "
                         f"| {scope} | `{item['evidence']}` |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def summary(root) -> Optional[Dict[str, Any]]:
    """Compact report for status views and MCP; None without factory.json."""
    data = load(root)
    if data is None:
        return None
    report = evaluate(root, data)
    upcoming = next_items(root, data, limit=10)
    return {**report, "next": upcoming}


def check(root) -> Tuple[List[str], List[str]]:
    """(errors, warnings) for tools/check.py; both empty without factory.json."""
    try:
        data = load(root)
    except PolierError as exc:
        return [f"factory: {exc}"], []
    if data is None:
        return [], []
    report = evaluate(root, data)
    return ([f"factory: {e}" for e in report["errors"]],
            [f"factory: {w}" for w in report["warnings"]])
