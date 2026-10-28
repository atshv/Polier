"""Human-in-the-loop approval records: ``reviews/approvals/AP-NNN.json``.

A high-risk action (new dependency, scope change, merge to base, release,
reopen of a done task, write to a protected path, forced state change) is
requested by a worker, granted or denied by the approver, and the record is the
approval. There is no expiry: a granted record counts until it is superseded.

One file per approval. An ID is ``AP-`` plus at least three digits, allocated
under a lock and reserved with ``O_CREAT | O_EXCL`` so two processes never get
the same number. Grant and deny append a ``runs/<task>.json`` ``approval``
event when the record names a task.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from .claims import parse_time, timestamp
from .errors import PolierError
from .policy import ACTIONS
from .runs import FileLock, append_event

APPROVALS = Path("reviews") / "approvals"
STATUSES = ("pending", "granted", "denied")
ID_PATTERN = re.compile(r"^AP-[0-9]{3,}$")
LOCK_SUFFIX = ".lock"
LOCK_NAME = ".allocate.lock"

# ---------------------------------------------------------------------------
# paths and storage
# ---------------------------------------------------------------------------

def _folder(root) -> Path:
    return Path(root) / APPROVALS


def _path(root, approval_id: str) -> Path:
    return _folder(root) / f"{approval_id}.json"


def valid_id(value) -> bool:
    """True for an approval ID of the form AP-001."""
    return isinstance(value, str) and bool(ID_PATTERN.fullmatch(value.strip()))


def _id_number(value) -> int:
    """The numeric part of an approval ID; a large number for an unreadable one."""
    if not valid_id(value):
        return 10 ** 9
    return int(value.strip().split("-", 1)[1])


def _id(task) -> str:
    if not isinstance(task, str) or not task.strip():
        raise PolierError("an approval needs a task id or null")
    task = task.strip()
    if "/" in task or "\\" in task or task in (".", ".."):
        raise PolierError(f"invalid task id for an approval: {task!r}")
    return task


def _by(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolierError("an approval needs who requested or decided it")
    return value.strip()


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _load(path: Path) -> Optional[dict]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def _write(path: Path, record: dict) -> None:
    """Write one approval atomically so a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    tmp.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _create(path: Path, record: dict) -> None:
    """Reserve a fresh approval file; FileExistsError when the ID is taken."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        os.write(fd, (json.dumps(record, indent=2) + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def _files(root) -> List[Path]:
    try:
        return sorted(_folder(root).glob("*.json"))
    except OSError:
        return []


def _sort_key(record: dict):
    return (_id_number(record.get("id")), str(record.get("id")))


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------

def load_all(root) -> List[dict]:
    """Every readable approval record, sorted by ID; broken files are skipped."""
    records = [record for record in (_load(path) for path in _files(root)) if record is not None]
    records.sort(key=_sort_key)
    return records


def get(root, approval_id) -> Optional[dict]:
    """The record of `approval_id`, or None (also for a malformed ID)."""
    if not valid_id(approval_id):
        return None
    return _load(_path(root, approval_id.strip()))


def _matches(record: dict, action: str, task: Optional[str]) -> bool:
    if record.get("action") != action:
        return False
    return _concerns(record, task)


def _concerns(record: dict, task: Optional[str]) -> bool:
    """True when the record concerns `task`; None matches any task (both ways)."""
    if task is None or record.get("task") is None:
        return True
    return record.get("task") == task


def _decided_key(record: dict):
    moment = parse_time(record.get("approved_at"))
    if moment is None:
        moment = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    return (moment, _id_number(record.get("id")))


def granted(root, action, task=None) -> Optional[dict]:
    """The newest granted record for `action`; a record without a task matches any task."""
    task = _id(task) if task is not None else None
    candidates = [record for record in load_all(root)
                  if record.get("status") == "granted" and _matches(record, action, task)]
    if not candidates:
        return None
    return max(candidates, key=_decided_key)


def pending(root, task=None) -> List[dict]:
    """The pending records, optionally only the ones that concern `task`."""
    task = _id(task) if task is not None else None
    records = [record for record in load_all(root)
               if record.get("status") == "pending" and _concerns(record, task)]
    records.sort(key=_sort_key)
    return records


def has_grant(root, action, task=None) -> bool:
    """True when a granted record for `action` covers `task`."""
    return granted(root, action, task) is not None


# ---------------------------------------------------------------------------
# writing
# ---------------------------------------------------------------------------

def _next_number(root) -> int:
    numbers = [_id_number(record.get("id")) for record in load_all(root)]
    numbers += [_id_number(path.stem) for path in _files(root) if valid_id(path.stem)]
    known = [number for number in numbers if number < 10 ** 9]
    return (max(known) + 1) if known else 1


def request(root, action: str, task=None, by: str = "worker", note: str = "") -> dict:
    """Request an approval; an identical pending record is reused.

    "Identical" means the same action, task, requester and note, so an agent
    that retries its request does not create a second record.
    """
    action = _action(action)
    task = _id(task) if task is not None else None
    by = _by(by)
    note = _text(note)
    folder = _folder(root)
    folder.mkdir(parents=True, exist_ok=True)
    with FileLock(folder / LOCK_NAME):
        for existing in load_all(root):
            if (existing.get("status") == "pending"
                    and existing.get("action") == action
                    and existing.get("task") == task
                    and existing.get("requested_by") == by
                    and _text(existing.get("note")) == note):
                return existing
        number = _next_number(root)
        while True:
            approval_id = f"AP-{number:03d}"
            record = {
                "id": approval_id,
                "action": action,
                "task": task,
                "status": "pending",
                "requested_by": by,
                "requested_at": timestamp(),
                "approved_by": None,
                "approved_at": None,
                "note": note or None,
            }
            try:
                _create(_path(root, approval_id), record)
            except FileExistsError:
                number += 1
                continue
            return record


def _action(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolierError("an approval needs an action")
    action = value.strip()
    if action not in ACTIONS:
        raise PolierError(
            f"unknown approval action {action!r} (known: {', '.join(ACTIONS)})")
    return action


def _decide(root, approval_id, by, note, status: str) -> dict:
    if not valid_id(approval_id):
        raise PolierError(
            f"invalid approval id {approval_id!r} (expected AP- plus at least 3 digits)")
    approval_id = approval_id.strip()
    by = _by(by)
    note = _text(note)
    path = _path(root, approval_id)
    with FileLock(path.with_name(path.name + LOCK_SUFFIX)):
        record = _load(path)
        if record is None:
            raise PolierError(f"no approval {approval_id}")
        current = record.get("status")
        if current != "pending":
            raise PolierError(f"approval {approval_id} is already {current}")
        record["status"] = status
        record["approved_by"] = by
        record["approved_at"] = timestamp()
        if note:
            old = _text(record.get("note"))
            record["note"] = f"{old} | {note}" if old else note
        _write(path, record)

    task = record.get("task")
    if isinstance(task, str) and task.strip():
        try:
            append_event(root, task, "approval", {
                "id": approval_id,
                "action": record.get("action"),
                "status": status,
                "by": by,
            })
        except Exception:  # noqa: BLE001 - the approval record is the source of truth
            pass
    return record


def grant(root, approval_id, by: str, note: str = "") -> dict:
    """Grant a pending approval; PolierError when it does not exist or is already decided."""
    return _decide(root, approval_id, by, note, "granted")


def deny(root, approval_id, by: str, note: str = "") -> dict:
    """Deny a pending approval; PolierError when it does not exist or is already decided."""
    return _decide(root, approval_id, by, note, "denied")


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

def errors(root, board=None) -> List[str]:
    """Every problem of the approval store; [] when the records are consistent.

    With `board`, an approval that names a task not on the board is an error;
    without it the task reference is not checked (the guard has no board).
    """
    problems: List[str] = []

    def add(path: Path, detail: str) -> None:
        problems.append(f"{APPROVALS.as_posix()}/{path.name}: {detail}")

    known_tasks = None
    if isinstance(board, dict) and isinstance(board.get("tasks"), list) and board["tasks"]:
        known_tasks = {task.get("id") for task in board["tasks"] if isinstance(task, dict)}
    seen: Dict[str, str] = {}
    for path in _files(root):
        record = _load(path)
        if record is None:
            add(path, "is not a JSON object")
            continue
        approval_id = record.get("id")
        if not valid_id(approval_id):
            add(path, f"id must be AP- plus at least 3 digits (is {approval_id!r})")
        elif approval_id.strip() != path.stem:
            add(path, f"id {approval_id!r} does not match the file name")
        else:
            if approval_id in seen:
                add(path, f"duplicate approval id {approval_id} (also in {seen[approval_id]})")
            else:
                seen[approval_id] = path.name
        if record.get("status") not in STATUSES:
            add(path, f"unknown status {record.get('status')!r} "
                      f"(known: {', '.join(STATUSES)})")
        if record.get("action") not in ACTIONS:
            add(path, f"unknown action {record.get('action')!r} "
                      f"(known: {', '.join(ACTIONS)})")
        if not _text(record.get("requested_by")):
            add(path, "requested_by is missing")
        if parse_time(record.get("requested_at")) is None:
            add(path, "requested_at is not an ISO 8601 timestamp")
        task = record.get("task")
        if task is not None:
            if not isinstance(task, str) or not task.strip():
                add(path, "task must be a task id or null")
            elif known_tasks is not None and task not in known_tasks:
                add(path, f"unknown task {task!r}")
        if record.get("status") == "granted":
            if not _text(record.get("approved_by")):
                add(path, "a granted record needs approved_by")
            if parse_time(record.get("approved_at")) is None:
                add(path, "a granted record needs approved_at")
    return problems
