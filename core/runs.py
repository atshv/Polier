"""Execution state of one task: ``runs/<ID>.json``.

The board is the plan state; a run record is the execution log of a task: the
attempts (one per run), the append-only event list (start, gate, review, state,
approval, note, escalate), the last result and the last update. One file per
task, committed, so a task can be audited after the fact.

Every write is atomic (temp file + ``os.replace``) under a ``<file>.lock``
created with ``O_CREAT | O_EXCL``; a lock older than 60 s is treated as
abandoned and removed, the pattern of ``core.claims``. A reader tolerates a
missing or broken file and falls back to an empty skeleton, so a half-written
file never stops the tools. ``record_gate`` never raises: the gate itself must
not fail because its run record could not be written.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Callable, Optional

from .claims import timestamp
from .errors import PolierError
from .policy import POLICY, enabled as policy_enabled, load_policy

RUNS = "runs"
STATES = ("idle", "running", "done", "failed", "blocked")
RESULTS = ("pass", "fail", "cancelled")
EVENT_KINDS = ("start", "gate", "review", "state", "approval", "note", "escalate")
MAX_EVENTS = 500

LOCK_SUFFIX = ".lock"
LOCK_TIMEOUT = 5.0   # seconds to wait for a store lock before giving up
LOCK_STALE = 60.0    # seconds after which an abandoned lock file is removed
RETRY_SLEEP = 0.02

_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
_STATE_RESULT = {"pass": "done", "fail": "failed", "cancelled": "blocked"}


class FileLock:
    """Cross-platform file lock: a lock file created with O_CREAT | O_EXCL.

    Shared by the 1.1 stores (run records, board.json, the approval counter);
    it is the lock of ``core.claims`` without the claim semantics.
    """

    def __init__(self, path: Path, timeout: float = LOCK_TIMEOUT):
        self.path = Path(path)
        self.timeout = timeout
        self.fd: Optional[int] = None

    def __enter__(self) -> "FileLock":
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
                        f"the store is busy ({self.path.name}); try again in a moment")
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


# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------

def _task_id(task) -> str:
    if not isinstance(task, str) or not task.strip():
        raise PolierError("a run record needs a task id")
    task = task.strip()
    if not _NAME.fullmatch(task) or task in (".", ".."):
        raise PolierError(f"invalid task id for a run record: {task!r}")
    return task


def run_path(root, task) -> Path:
    """``<root>/runs/<ID>.json``; raises PolierError for an invalid task id."""
    return Path(root) / RUNS / f"{_task_id(task)}.json"


def _skeleton(task: str) -> dict:
    return {"task": task, "state": "idle", "attempt": 0, "attempts": [], "events": [],
            "updated": None}


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _clean_attempt(entry, index: int) -> dict:
    entry = entry if isinstance(entry, dict) else {}
    number = entry.get("n")
    result = entry.get("result")
    return {
        "n": number if _is_int(number) and number > 0 else index + 1,
        "started": entry.get("started") if isinstance(entry.get("started"), str) else None,
        "ended": entry.get("ended") if isinstance(entry.get("ended"), str) else None,
        "result": result if result in RESULTS else None,
        "note": entry.get("note") if isinstance(entry.get("note"), str) else None,
    }


def _clean_event(entry) -> Optional[dict]:
    if not isinstance(entry, dict):
        return None
    kind = entry.get("kind")
    data = entry.get("data")
    return {
        "at": entry.get("at") if isinstance(entry.get("at"), str) else None,
        "kind": kind if isinstance(kind, str) and kind else "note",
        "data": data if isinstance(data, dict) else {},
    }


def _clean(task: str, raw) -> dict:
    record = _skeleton(task)
    if not isinstance(raw, dict):
        return record
    if isinstance(raw.get("task"), str) and raw["task"].strip():
        record["task"] = raw["task"].strip()
    state = raw.get("state")
    record["state"] = state if state in STATES else "idle"
    attempt = raw.get("attempt")
    record["attempt"] = attempt if _is_int(attempt) and attempt >= 0 else 0
    attempts = raw.get("attempts")
    if isinstance(attempts, list):
        record["attempts"] = [_clean_attempt(entry, index) for index, entry in enumerate(attempts)]
    events = raw.get("events")
    if isinstance(events, list):
        cleaned = [_clean_event(entry) for entry in events]
        record["events"] = [entry for entry in cleaned if entry is not None][-MAX_EVENTS:]
    record["attempt"] = max(record["attempt"], len(record["attempts"]))
    updated = raw.get("updated")
    record["updated"] = updated if isinstance(updated, str) else None
    return record


def _read(path: Path, task: str) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _skeleton(task)
    return _clean(task, raw)


def _write(path: Path, record: dict) -> None:
    """Write a run record atomically so a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    tmp.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _update(root, task, change: Callable[[dict], None], moment: Optional[str] = None) -> dict:
    """Read-modify-write one run record under its lock; `change` edits the dict in place."""
    task = _task_id(task)
    path = run_path(root, task)
    moment = moment or timestamp()
    with FileLock(path.with_name(path.name + LOCK_SUFFIX)):
        record = _read(path, task)
        change(record)
        record["updated"] = moment
        _write(path, record)
        return record


def _trim(record: dict) -> None:
    if len(record["events"]) > MAX_EVENTS:
        record["events"] = record["events"][-MAX_EVENTS:]


def _event(kind: str, data, moment: str) -> dict:
    return {"at": moment, "kind": kind, "data": dict(data) if isinstance(data, dict) else {}}


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def enabled(root) -> bool:
    """True when the project has a ``policy.json`` (the 1.1 stores are in use)."""
    try:
        return (Path(root) / POLICY).is_file()
    except OSError:
        return False


def load_run(root, task) -> dict:
    """The run record of `task`, or an empty skeleton when it is missing or broken."""
    task = _task_id(task)
    return _read(run_path(root, task), task)


def append_event(root, task, kind, data=None, at=None) -> dict:
    """Append one event and return the stored record (the last 500 events are kept)."""
    task = _task_id(task)
    kind = kind if isinstance(kind, str) and kind else "note"
    moment = at or timestamp()

    def change(record: dict) -> None:
        record["events"].append(_event(kind, data, moment))
        _trim(record)

    return _update(root, task, change, moment)


def start_attempt(root, task, actor=None) -> dict:
    """Open the next attempt: attempt += 1, state running, a ``start`` event."""
    task = _task_id(task)
    moment = timestamp()

    def change(record: dict) -> None:
        record["attempt"] = int(record.get("attempt") or 0) + 1
        record["attempts"].append({
            "n": record["attempt"], "started": moment, "ended": None,
            "result": None, "note": None,
        })
        record["state"] = "running"
        record["events"].append(_event("start", {"actor": actor}, moment))
        _trim(record)

    return _update(root, task, change, moment)


def finish_attempt(root, task, result, note=None) -> dict:
    """Close the open attempt with `result`, or record the result when none is open.

    `result` is ``pass``, ``fail`` or ``cancelled`` and moves the run state to
    ``done``, ``failed`` or ``blocked`` respectively.
    """
    if result not in RESULTS:
        raise PolierError(f"unknown attempt result {result!r} (known: {', '.join(RESULTS)})")
    task = _task_id(task)
    moment = timestamp()

    def change(record: dict) -> None:
        open_attempt = next((entry for entry in reversed(record["attempts"])
                             if entry.get("ended") is None), None)
        if open_attempt is not None:
            open_attempt["ended"] = moment
            open_attempt["result"] = result
            if note is not None:
                open_attempt["note"] = note
        record["state"] = _STATE_RESULT[result]

    return _update(root, task, change, moment)


def attempt_count(root, task) -> int:
    """How many attempts the task has used."""
    return int(load_run(root, task).get("attempt") or 0)


def run_state(root, task) -> str:
    """idle, running, done, failed or blocked."""
    return load_run(root, task)["state"]


def exhausted(root, task, limit) -> bool:
    """True when the task used its attempt limit and is not done."""
    if not _is_int(limit):
        return False
    return attempt_count(root, task) >= limit and run_state(root, task) != "done"


def last_event(root, task) -> Optional[dict]:
    """The newest event of the task, or None."""
    events = load_run(root, task)["events"]
    return events[-1] if events else None


def record_gate(root, task, gate, result, record) -> Optional[dict]:
    """Append a ``gate`` event when the project uses a policy; never raises."""
    try:
        if not enabled(root):
            return None
        try:
            policy = load_policy(root)
        except PolierError:
            return None
        if not policy_enabled(policy):
            return None
        return append_event(root, task, "gate", {
            "gate": str(gate), "result": str(result), "record": str(record)})
    except Exception:  # noqa: BLE001 - a gate must never fail because of its run record
        return None


def summary(root, task) -> dict:
    """The condensed run record: task, state, attempt, attempts, last_event, updated."""
    record = load_run(root, task)
    events = record["events"]
    return {
        "task": record["task"],
        "state": record["state"],
        "attempt": record["attempt"],
        "attempts": record["attempts"],
        "last_event": events[-1] if events else None,
        "updated": record["updated"],
    }
