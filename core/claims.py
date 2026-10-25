"""Cross-harness task claims with a heartbeat (PL-04).

A claim says "this session works on this task right now". It lives in
``<git-common-dir>/polier/claims/<task>.json``, shared by every worktree of the
repository, so a DeepSeek Harness session and a Claude Code session see each
other. ``board.json`` is never written here: claims are runtime state, not plan
state (that keeps parallel sessions from creating merge conflicts).

A claim is live while ``now - heartbeat < ttl`` (default 600 s). The holder
refreshes the heartbeat (``beat``) or re-takes its own claim (``take`` with the
same session). A stale claim may be taken over by another session.

Files are rewritten atomically (temp file + ``os.replace``) under a
``<task>.json.lock`` file created with ``O_CREAT | O_EXCL``, so two processes
cannot both take the same task. Standard library only, Python 3.9+.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
from pathlib import Path
from typing import List, Optional

from .errors import PolierError
from .paths import git_common_dir

HARNESSES = ("dsh", "claude-code", "cli")
CLAIM_FIELDS = ("task", "harness", "session", "worktree", "slot", "started", "heartbeat")
TTL = 600.0

LOCK_SUFFIX = ".lock"
LOCK_TIMEOUT = 5.0   # seconds to wait for the claim lock before giving up
LOCK_STALE = 60.0    # seconds after which an abandoned lock file is removed
RETRY_SLEEP = 0.02


class ClaimConflict(PolierError):
    """The task is claimed by another live session."""


class NoClaim(PolierError):
    """There is no claim for that task (or not one held by this session)."""


# ---------------------------------------------------------------------------
# time helpers
# ---------------------------------------------------------------------------

def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def timestamp(moment: Optional[dt.datetime] = None) -> str:
    """ISO 8601 UTC timestamp with seconds precision, e.g. 2026-10-25T02:41:41+00:00."""
    moment = moment or _now()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def parse_time(value) -> Optional[dt.datetime]:
    """A claim timestamp as an aware UTC datetime, or None when unreadable."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        moment = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone(dt.timezone.utc)


def claim_age(claim: dict, now: Optional[dt.datetime] = None) -> Optional[float]:
    """Seconds since the claim's last heartbeat, or None when the claim has no readable heartbeat."""
    beat = parse_time((claim or {}).get("heartbeat"))
    if beat is None:
        return None
    return ((now or _now()) - beat).total_seconds()


def is_live(claim: dict, ttl: float = TTL, now: Optional[dt.datetime] = None) -> bool:
    """True while the claim's heartbeat is younger than `ttl` seconds."""
    age = claim_age(claim, now)
    return age is not None and age < float(ttl)


# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------

def _valid_task(task) -> str:
    if not isinstance(task, str) or not task.strip():
        raise PolierError("a claim needs a task id")
    task = task.strip()
    if task in (".", "..") or "/" in task or "\\" in task:
        raise PolierError(f"invalid task id for a claim: {task!r}")
    return task


def claim_dir(root) -> Path:
    """The claims folder shared by every worktree of the project (`<git-common-dir>/polier/claims`)."""
    return Path(git_common_dir(root)) / "polier" / "claims"


def _path(root, task: str) -> Path:
    return claim_dir(root) / f"{task}.json"


def _load(path: Path) -> Optional[dict]:
    try:
        claim = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return claim if isinstance(claim, dict) else None


def _write(path: Path, claim: dict) -> None:
    """Write a claim atomically so a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    tmp.write_text(json.dumps(claim, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class _Lock:
    """Cross-platform claim lock: a file created with O_CREAT | O_EXCL."""

    def __init__(self, path: Path, timeout: float = LOCK_TIMEOUT):
        self.path = path
        self.timeout = timeout
        self.fd: Optional[int] = None

    def __enter__(self) -> "_Lock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                os.write(self.fd, f"{os.getpid()}\n".encode("ascii"))
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > LOCK_STALE:
                        self.path.unlink()   # abandoned lock of a crashed process
                        continue
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise PolierError(
                        f"the claim store is busy ({self.path.name}); try again in a moment")
                time.sleep(RETRY_SLEEP)
            except FileNotFoundError:  # the folder vanished between mkdir and open
                self.path.parent.mkdir(parents=True, exist_ok=True)

    def __exit__(self, *_exc) -> None:
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
        try:
            self.path.unlink()
        except OSError:
            pass


def _holder(claim: dict) -> str:
    return (f"{claim.get('harness') or 'unknown harness'} session "
            f"{claim.get('session') or 'unknown'}")


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def take(root, task: str, *, harness: str, session: str, worktree=None,
         slot=None, ttl: float = TTL) -> dict:
    """Claim `task` for `session`, or refresh a claim the same session already holds.

    A live claim held by another session raises ClaimConflict naming the holder.
    A stale claim is taken over. Returns the stored claim.
    """
    task = _valid_task(task)
    if harness not in HARNESSES:
        raise PolierError(f"unknown harness {harness!r} (known: {', '.join(HARNESSES)})")
    if not isinstance(session, str) or not session.strip():
        raise PolierError("a claim needs a session id")
    session = session.strip()
    path = _path(root, task)
    now = _now()
    with _Lock(path.with_name(path.name + LOCK_SUFFIX)):
        existing = _load(path)
        if existing and existing.get("session") == session:
            claim = dict(existing)
            claim["harness"] = harness
            claim["heartbeat"] = timestamp(now)
            if worktree is not None:
                claim["worktree"] = worktree or None
            if slot is not None:
                claim["slot"] = slot
            _write(path, claim)
            return claim
        if existing and is_live(existing, ttl, now):
            raise ClaimConflict(
                f"task {task} is claimed by {_holder(existing)} "
                f"(heartbeat {existing.get('heartbeat')}, started {existing.get('started')})")
        claim = {
            "task": task,
            "harness": harness,
            "session": session,
            "worktree": worktree or None,
            "slot": slot if isinstance(slot, int) and not isinstance(slot, bool) else None,
            "started": timestamp(now),
            "heartbeat": timestamp(now),
        }
        _write(path, claim)
        return claim


def release(root, task: str, session: Optional[str] = None) -> bool:
    """Remove the claim of `task`; with `session`, only when that session holds it.

    Returns True when a claim was removed, False when there was nothing to
    release (or the claim belongs to another session).
    """
    task = _valid_task(task)
    path = _path(root, task)
    with _Lock(path.with_name(path.name + LOCK_SUFFIX)):
        claim = _load(path)
        if claim is None:
            return False
        if session is not None and claim.get("session") != session:
            return False
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        return True


def beat(root, task: str, session: Optional[str] = None) -> dict:
    """Refresh the heartbeat of a claim; raises NoClaim when missing and ClaimConflict on a foreign claim."""
    task = _valid_task(task)
    path = _path(root, task)
    with _Lock(path.with_name(path.name + LOCK_SUFFIX)):
        claim = _load(path)
        if claim is None:
            raise NoClaim(f"no claim for task {task}")
        if session is not None and claim.get("session") != session:
            raise ClaimConflict(
                f"task {task} is claimed by {_holder(claim)}")
        claim = dict(claim)
        claim["heartbeat"] = timestamp()
        _write(path, claim)
        return claim


def read_claim(root, task: str) -> Optional[dict]:
    """The stored claim of `task`, or None when there is none (or it is unreadable)."""
    try:
        task = _valid_task(task)
        return _load(_path(root, task))
    except PolierError:
        return None


def live_claims(root, ttl: float = TTL) -> List[dict]:
    """Every live claim of the repository, sorted by task; stale claims are left out."""
    try:
        folder = claim_dir(root)
    except PolierError:
        return []
    now = _now()
    claims: List[dict] = []
    try:
        paths = sorted(folder.glob("*.json"))
    except OSError:
        return []
    for path in paths:
        claim = _load(path)
        if claim is not None and is_live(claim, ttl, now):
            claims.append(claim)
    claims.sort(key=lambda c: str(c.get("task")))
    return claims
