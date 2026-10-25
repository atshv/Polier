"""Exclusive resource locks shared by every worktree of a repo (PL-03).

A lock is a JSON file in ``<git-common-dir>/polier/locks/<resource>.lock`` that
names the current holder (task, slot, harness, pid, host, started). Creation is
atomic (``O_CREAT | O_EXCL``). A stale lock - the holder pid is gone on this
host, or the lock is older than ``ttl`` - is taken over atomically (temp file +
``os.replace``) and reported with a warning. The caller releases the lock,
normally in a ``finally`` block; ``release_lock`` is the stable counterpart of
``acquire_lock``.

Standard library only, Python 3.9+.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import socket
import time
from pathlib import Path
from typing import Callable, Optional

from .errors import PolierError
from .paths import git_common_dir

SAFE_RESOURCE = re.compile(r"^[A-Za-z0-9._-]+$")
HOLDER_KEYS = ("task", "slot", "harness", "pid", "host", "started")
# A lock file created but not yet filled in is ignored for a moment instead of
# being taken over, so an in-flight writer is not robbed of its lock.
UNREADABLE_GRACE = 5.0


def _iso(moment: Optional[dt.datetime] = None) -> str:
    moment = moment or dt.datetime.now(dt.timezone.utc)
    return moment.isoformat(timespec="seconds")


def valid_resource(resource) -> bool:
    """True for a resource name that is safe as a file name."""
    name = str(resource if resource is not None else "")
    return bool(SAFE_RESOURCE.fullmatch(name)) and name not in (".", "..")


def lock_path(root, resource) -> Path:
    """``<git-common-dir>/polier/locks/<resource>.lock`` for the repo of `root`."""
    name = str(resource if resource is not None else "")
    if not valid_resource(name):
        raise PolierError(
            f"invalid lock resource {name!r}: use letters, digits, '.', '_' and '-'")
    return git_common_dir(root) / "polier" / "locks" / f"{name}.lock"


def read_lock(root, resource) -> Optional[dict]:
    """The holder of the lock, or None when the lock does not exist or is unreadable."""
    try:
        data = json.loads(lock_path(root, resource).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return None
    return data if isinstance(data, dict) else None


def release_lock(root, resource) -> bool:
    """Remove the lock; True when a lock file was removed."""
    try:
        lock_path(root, resource).unlink()
    except FileNotFoundError:
        return False
    except OSError:
        return False
    return True


def acquire_lock(root, resource, holder, wait: float = 1800.0, ttl: float = 3600.0,
                 poll: float = 1.0, now: Optional[Callable[[], float]] = None,
                 on_wait: Optional[Callable[[Optional[dict], float], None]] = None) -> dict:
    """Take the lock, waiting at most `wait` seconds for a live holder to finish.

    Returns ``{"acquired", "waited", "holder", "taken_over", "warning"}``:
    `holder` is the holder dict that now owns the lock (or the blocker when the
    wait ran out), `waited` is in seconds, `taken_over` marks a stale lock that
    was replaced. `now` is a clock returning epoch seconds (default time.time),
    `on_wait(holder, waited)` is called after every poll while the lock stays busy.
    """
    clock = _clock(now)
    path = lock_path(root, resource)
    ours = _normalized_holder(holder)
    started_at = clock()
    waited = 0.0
    outcome = {
        "acquired": False,
        "waited": 0.0,
        "holder": None,
        "taken_over": False,
        "warning": None,
    }
    while True:
        if _create(path, ours):
            # waited stays 0.0 when the lock was free right away.
            outcome.update(acquired=True, waited=round(waited, 3), holder=ours)
            return outcome
        existing = read_lock(root, resource)
        reason = _stale_reason(path, existing, ttl, clock())
        if reason:
            warning = (f"stale lock on {resource} taken over ({reason}; "
                       f"previous holder {_describe(existing)})")
            if _take_over(path, ours, _snapshot(path)):
                outcome.update(acquired=True, waited=round(waited, 3), holder=ours,
                               taken_over=True, warning=warning)
                return outcome
            continue  # somebody else changed the lock; look again
        waited = _elapsed(clock, started_at)
        if waited >= float(wait):
            outcome.update(holder=existing, waited=waited)
            return outcome
        pause = float(poll) if poll is not None and float(poll) > 0 else 0.05
        time.sleep(max(0.0, min(pause, float(wait) - waited)))
        waited = _elapsed(clock, started_at)
        if on_wait is not None:
            on_wait(read_lock(root, resource), waited)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _clock(now):
    """A function returning epoch seconds, from None, a callable or a fixed value."""
    if now is None:
        return time.time

    def current() -> float:
        value = now() if callable(now) else now
        if isinstance(value, dt.datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=dt.timezone.utc)
            return value.timestamp()
        return float(value)

    return current


def _elapsed(clock, start: float) -> float:
    return round(max(0.0, float(clock()) - start), 3)


def _normalized_holder(holder) -> dict:
    data = dict(holder or {})
    data.setdefault("pid", os.getpid())
    data.setdefault("host", socket.gethostname())
    data.setdefault("started", _iso())
    for key in HOLDER_KEYS:
        data.setdefault(key, None)
    return data


def _describe(holder: Optional[dict]) -> str:
    if not holder:
        return "unknown"
    task = holder.get("task") or "unknown"
    harness = holder.get("harness") or "unknown"
    pid = holder.get("pid")
    return f"{task} ({harness}, pid {pid if pid is not None else '?'})"


def _pid_alive(pid) -> bool:
    try:
        number = int(pid)
    except (TypeError, ValueError):
        return False
    if number <= 0:
        return False
    try:
        os.kill(number, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _mtime_age(path: Path, now_epoch: float) -> Optional[float]:
    try:
        return now_epoch - path.stat().st_mtime
    except OSError:
        return None


def _started_epoch(holder: Optional[dict], path: Path) -> float:
    value = (holder or {}).get("started")
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            moment = dt.datetime.fromisoformat(text)
        except ValueError:
            moment = None
        if moment is not None:
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=dt.timezone.utc)
            return moment.timestamp()
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _stale_reason(path: Path, holder: Optional[dict], ttl, now_epoch: float) -> Optional[str]:
    if not holder:
        age = _mtime_age(path, now_epoch)
        if age is None or age < UNREADABLE_GRACE:
            return None
        return "the lock file is empty or unreadable"
    host = holder.get("host")
    if isinstance(host, str) and host and host == socket.gethostname():
        pid = holder.get("pid")
        if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0 and not _pid_alive(pid):
            return f"holder process {pid} is gone"
    if ttl is not None and float(ttl) >= 0:
        age = now_epoch - _started_epoch(holder, path)
        if age > float(ttl):
            return f"lock is {int(age)}s old (ttl {int(float(ttl))}s)"
    return None


def _create(path: Path, holder: dict) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return False
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(holder, indent=2) + "\n")
            stream.flush()
    except OSError:
        try:
            os.unlink(str(path))
        except OSError:
            pass
        return False
    return True


def _snapshot(path: Path) -> Optional[bytes]:
    try:
        return path.read_bytes()
    except OSError:
        return None


def _take_over(path: Path, holder: dict, snapshot: Optional[bytes]) -> bool:
    """Replace a stale lock atomically, unless it changed since `snapshot` was read."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.takeover-{os.getpid()}-{time.monotonic_ns()}")
    try:
        temp.write_text(json.dumps(holder, indent=2) + "\n", encoding="utf-8")
        if _snapshot(path) != snapshot:
            return False
        os.replace(str(temp), str(path))
        return True
    finally:
        try:
            temp.unlink()
        except OSError:
            pass
