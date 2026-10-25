"""Runtime slots: one port set, test database and bucket per worktree (PL-02).

Slot 0 belongs to the owner's main checkout. Worktrees get the lowest free
slot ``1 ... resources.slots - 1``. The slot is written to ``.polier-slot`` in
the worktree root and registered in ``<git-common-dir>/polier/slots.json``,
which every worktree of the repo shares. A small file lock around the registry
keeps two parallel ``acquire`` calls from handing out the same slot.

Polier does not create databases or buckets; it only derives their names from
``board.json -> resources`` (defaults: 3 slots, port base 4000, stride 100).

Standard library only, Python 3.9+.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from .board import load_board, resources
from .errors import PolierError
from .paths import git_common_dir, is_main_checkout, main_checkout

SLOT_FILE = ".polier-slot"
REGISTRY_VERSION = 1
LOCK_TIMEOUT = 10.0

try:  # POSIX; Windows falls back to an O_CREAT|O_EXCL lock file
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - Windows only
    _fcntl = None


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _worktree_root(root) -> Path:
    """The git working-tree root containing `root` (so a subfolder still means its worktree)."""
    folder = Path(root).resolve()
    try:
        result = subprocess.run(["git", "-C", str(folder), "rev-parse", "--show-toplevel"],
                                capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return folder
    top = (result.stdout or "").strip()
    if result.returncode == 0 and top:
        return Path(top).resolve()
    return folder


def slot_path(root) -> Path:
    """`<root>/.polier-slot`."""
    return Path(root).resolve() / SLOT_FILE


def registry_path(root) -> Path:
    """`<git-common-dir>/polier/slots.json`, shared by every worktree."""
    return git_common_dir(root) / "polier" / "slots.json"


def load_slot(root) -> Optional[dict]:
    """The parsed `.polier-slot` of the worktree, or None."""
    data = _read_json(slot_path(_worktree_root(root)))
    return data if isinstance(data, dict) else None


def list_slots(root) -> List[dict]:
    """Every registered slot sorted by number, each with `stale` (`worktree` folder gone)."""
    registry = _read_registry(_worktree_root(root))
    listed: List[dict] = []
    for key, entry in registry["slots"].items():
        try:
            number = int(key)
        except (TypeError, ValueError):
            continue
        record = dict(entry)
        record["slot"] = number
        record["stale"] = not _tree_exists(entry.get("worktree"))
        listed.append(record)
    listed.sort(key=lambda item: item["slot"])
    return listed


def acquire(root, reclaim_stale: bool = False) -> dict:
    """Take the worktree's slot (reusing `.polier-slot`), or slot 0 in the main checkout.

    Raises PolierError outside git and when every worktree slot is taken; a
    failed acquire changes nothing. `reclaim_stale=True` may reuse slots whose
    worktree folder no longer exists.
    """
    root = _worktree_root(root)
    checkout = main_checkout(root)  # PolierError when root is not inside git
    board = load_board(checkout, strict=False)
    settings = resources(board)
    project = _project_name(board, checkout)

    if is_main_checkout(root):
        existing = load_slot(root)
        if _valid_slot(existing, root) and existing.get("slot") == 0:
            return existing
        data = _slot_data(0, root, project, settings)
        _write_json(slot_path(root), data)
        return data

    existing = load_slot(root)
    if _valid_slot(existing, root) and existing.get("slot") != 0:
        reused = _reuse(root, existing)
        if reused is not None:
            return reused

    with _registry_lock(root):
        registry = _read_registry(root)
        registered = registry["slots"]
        if reclaim_stale:
            for key in list(registered):
                if not _tree_exists(registered[key].get("worktree")):
                    del registered[key]
        try:
            limit = int(settings["slots"])
        except (TypeError, ValueError):
            limit = 3
        limit = max(1, limit)
        candidates = list(range(1, limit))
        own = _own_slot(registered, root)
        taken = {int(key) for key in registered if _int_key(key) is not None and int(key) != own}
        free = [number for number in candidates if number not in taken]
        if own is not None and own in candidates:
            chosen = own
        elif free:
            chosen = free[0]
        else:
            raise PolierError(
                f"no free slot: every slot 1..{max(1, limit) - 1} of project {project!r} "
                f"is taken — release one with `python3 tools/slot.py release` in its worktree "
                f"or rerun acquire with --reclaim-stale")
        data = _slot_data(chosen, root, project, settings)
        registered[str(chosen)] = data
        _write_registry(root, registry)
        _write_json(slot_path(root), data)
        return data


def release(root) -> Optional[dict]:
    """Remove `.polier-slot` and the registry entry; returns the removed slot data."""
    root = _worktree_root(root)
    path = slot_path(root)
    if not path.is_file():
        return None
    data = load_slot(root)
    number = data.get("slot") if isinstance(data, dict) else None
    if isinstance(number, int) and not isinstance(number, bool) and number != 0:
        registry_path(root)  # fail early, outside git, before removing anything
    try:
        path.unlink()
    except OSError:
        return None
    if not isinstance(data, dict):
        return None
    if isinstance(number, int) and not isinstance(number, bool) and number != 0:
        with _registry_lock(root):
            registry = _read_registry(root)
            entry = registry["slots"].get(str(number))
            if entry is not None and _same_tree(entry.get("worktree"), root):
                del registry["slots"][str(number)]
                _write_registry(root, registry)
    return data


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _project_name(board: Optional[dict], checkout: Path) -> str:
    project = (board or {}).get("project")
    if isinstance(project, str) and project.strip():
        return project.strip()
    return checkout.name


def _slot_data(number: int, worktree: Path, project: str, settings: dict) -> Dict[str, object]:
    base = int(settings["port_base"])
    stride = int(settings["port_stride"])
    ports: Dict[str, int] = {}
    services = settings.get("services") or {}
    for name, offset in services.items():
        ports[str(name)] = base + stride * number + int(offset)
    return {
        "slot": number,
        "worktree": str(worktree),
        "project": project,
        "ports": ports,
        "db_name": f"{project}_slot_{number}",
        "bucket": f"{project}-slot-{number}",
        "acquired": _now(),
    }


def _valid_slot(data: Optional[dict], root: Path) -> bool:
    if not isinstance(data, dict):
        return False
    number = data.get("slot")
    if not isinstance(number, int) or isinstance(number, bool) or number < 0:
        return False
    if not _same_tree(data.get("worktree"), root):
        return False
    return (isinstance(data.get("ports"), dict)
            and isinstance(data.get("db_name"), str)
            and isinstance(data.get("bucket"), str))


def _same_tree(worktree, root: Path) -> bool:
    return isinstance(worktree, str) and bool(worktree) and os.path.abspath(worktree) == str(root)


def _tree_exists(worktree) -> bool:
    return isinstance(worktree, str) and bool(worktree) and Path(worktree).is_dir()


def _int_key(key) -> Optional[int]:
    try:
        return int(key)
    except (TypeError, ValueError):
        return None


def _own_slot(registered: dict, root: Path) -> Optional[int]:
    for key, entry in registered.items():
        number = _int_key(key)
        if number is not None and _same_tree(entry.get("worktree"), root):
            return number
    return None


def _reuse(root: Path, existing: dict) -> Optional[dict]:
    """Keep an existing `.polier-slot`, registering it again if the registry lost it.

    None means another worktree holds that number in the registry; the caller
    then acquires a fresh slot.
    """
    number = int(existing["slot"])
    with _registry_lock(root):
        registry = _read_registry(root)
        entry = registry["slots"].get(str(number))
        if entry is not None and _same_tree(entry.get("worktree"), root):
            return existing
        if entry is not None:
            return None
        registry["slots"][str(number)] = existing
        _write_registry(root, registry)
        return existing


# ---------------------------------------------------------------------------
# registry file and its cross-process lock
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    temp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(str(temp), str(path))


def _read_registry(root) -> dict:
    data = _read_json(registry_path(root))
    raw = data.get("slots") if isinstance(data, dict) else None
    slots: Dict[str, dict] = {}
    if isinstance(raw, dict):
        for key, entry in raw.items():
            number = _int_key(key)
            if number is not None and isinstance(entry, dict):
                slots[str(number)] = entry
    return {"version": REGISTRY_VERSION, "slots": slots}


def _write_registry(root, registry: dict) -> None:
    slots = registry["slots"]
    ordered = {str(number): slots[str(number)] for number in sorted(
        (number for number in (_int_key(key) for key in slots) if number is not None))}
    _write_json(registry_path(root), {"version": REGISTRY_VERSION, "slots": ordered})


@contextlib.contextmanager
def _registry_lock(root) -> Iterator[None]:
    """Exclusive cross-process lock for read-modify-write of the slot registry."""
    directory = registry_path(root).parent
    directory.mkdir(parents=True, exist_ok=True)
    lockfile = directory / "slots.lock"
    if _fcntl is not None:
        # flock on a sidecar file: the registry itself is replaced atomically,
        # which would drop a lock held on its inode.
        with open(str(lockfile), "a+") as handle:
            _fcntl.flock(handle.fileno(), _fcntl.LOCK_EX)
            try:
                yield
            finally:
                try:
                    _fcntl.flock(handle.fileno(), _fcntl.LOCK_UN)
                except OSError:  # pragma: no cover - defensive
                    pass
        return
    # Portable fallback: O_CREAT|O_EXCL lock file with a stale-after timeout.
    deadline = time.time() + LOCK_TIMEOUT
    while True:
        try:
            descriptor = os.open(str(lockfile), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            break
        except FileExistsError:
            if time.time() >= deadline:
                raise PolierError(f"the slot registry is locked: {lockfile}")
            time.sleep(0.02)
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii", "replace"))
        os.close(descriptor)
        yield
    finally:
        try:
            os.unlink(str(lockfile))
        except OSError:
            pass
