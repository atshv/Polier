"""Gate records: run one gate command, keep the full output, write a checksummed record.

A record classifies the run as ``pass``, ``fail``, ``timeout``, ``busy`` or
``infra``; the last one means the output looks like an infrastructure problem
(connection refused, port in use, a project pattern) and not like a test
failure. ``exclusive`` resources are protected by ``core.locks`` so two gates
that need the same resource never run at the same time.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import socket
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence, Union

from .locks import acquire_lock, release_lock

EVIDENCE = Path("reviews") / "evidence"
NAME = re.compile(r"[A-Za-z0-9_.-]+")
ERROR_LINE = re.compile(r"error|fail|traceback|exception|assert|panic|fatal", re.IGNORECASE)

# Lower-case fragments; the gate output is lower-cased before matching. The
# project may add its own patterns through board.json -> resources.infra_patterns.
DEFAULT_INFRA_PATTERNS = (
    "econnrefused",
    "err_connection_refused",
    "eaddrinuse",
    "is already used, make sure that nothing is running on the port",
    "address already in use",
)
RESULTS = ("pass", "fail", "timeout", "busy", "infra")
BUSY_EXIT = 75


def valid_name(value: str) -> bool:
    """Task IDs and gate names may only contain letters, digits, '.', '_' and '-'."""
    return bool(NAME.fullmatch(value or ""))


def git(root: Path, *args: str) -> Optional[str]:
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None
    return result.stdout if result.returncode == 0 else None


def new_base(folder: Path, stem: str) -> Path:
    """A path stem in `folder` for which neither .log nor .json exists yet."""
    base = folder / stem
    n = 2
    while (folder / f"{base.name}.log").exists() or (folder / f"{base.name}.json").exists():
        base = folder / f"{stem}-{n}"
        n += 1
    return base


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify(exit_code: int, output: str, infra_patterns=None, timed_out: bool = False) -> str:
    """`pass`, `fail`, `timeout` or `infra` for one finished gate run."""
    if timed_out:
        return "timeout"
    if exit_code == 0:
        return "pass"
    text = str(output or "").lower()
    for pattern in _infra_patterns(infra_patterns):
        if pattern in text:
            return "infra"
    return "fail"


def _infra_patterns(extra=None) -> List[str]:
    patterns = list(DEFAULT_INFRA_PATTERNS)
    for pattern in extra or ():
        if isinstance(pattern, str) and pattern.strip():
            lowered = pattern.strip().lower()
            if lowered not in patterns:
                patterns.append(lowered)
    return patterns


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _holder_text(holder: Optional[dict]) -> str:
    holder = holder or {}
    pid = holder.get("pid")
    return (f"{holder.get('task') or 'unknown'} ({holder.get('harness') or 'unknown'}, "
            f"pid {pid if pid is not None else '?'}) "
            f"since {holder.get('started') or '?'}")


def _busy_line(resource: str, holder: Optional[dict]) -> str:
    return (f"[gate.py] resource {resource} busy — held by {_holder_text(holder)}; rerun alone")


def write_record(task: str, name: str, root, *, command, exit_code: int, output: str,
                 result: Optional[str] = None, slot: Optional[int] = None, exclusive=(),
                 lock_wait_s: float = 0.0, started: Optional[dt.datetime] = None,
                 finished: Optional[dt.datetime] = None,
                 lock_warning: Optional[str] = None) -> dict:
    """Write <root>/reviews/evidence/<task>-<name>-<UTC>.log and .json; never overwrite.

    The same record fields as a gate run: task, gate, command, exit_code,
    started, finished, commit, dirty, log, log_sha256, plus slot, exclusive,
    lock_wait_s, result and lock_warning. Returns the record plus `output`,
    `log_path`, `record_path` and `root`.
    """
    if not valid_name(task) or not valid_name(name):
        raise ValueError("--task and --name may only contain letters, digits, '.', '_' and '-'")
    root = Path(root).resolve()
    folder = root / EVIDENCE
    folder.mkdir(parents=True, exist_ok=True)
    started = started or _utcnow()
    finished = finished or _utcnow()
    shown = " ".join(str(command if command is not None else "").split())
    base = new_base(folder, f"{task}-{name}-{started.strftime('%Y%m%dT%H%M%SZ')}")
    log, record_path = folder / f"{base.name}.log", folder / f"{base.name}.json"
    commit = (git(root, "rev-parse", "HEAD") or "").strip() or None
    status = git(root, "status", "--porcelain")

    code = int(exit_code)
    log.write_text(f"$ {shown}\n[exit {code}]\n\n{output or ''}", encoding="utf-8")
    record = {
        "task": task,
        "gate": name,
        "command": shown,
        "exit_code": code,
        "result": result,
        "slot": slot,
        "exclusive": [str(item) for item in exclusive or ()],
        "lock_wait_s": round(float(lock_wait_s or 0.0), 3),
        "lock_warning": lock_warning,
        "started": started.isoformat(timespec="seconds"),
        "finished": finished.isoformat(timespec="seconds"),
        "commit": commit,
        "dirty": bool(status.strip()) if status is not None else None,
        "log": log.name,
        "log_sha256": sha256(log),
    }
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return {**record, "output": output or "", "log_path": log, "record_path": record_path, "root": root}


def run_gate(command: Union[str, Sequence[str]], task: str, name: str, root=".", *,
             shell: bool = False, timeout: int = 600, slot: Optional[int] = None,
             exclusive=(),
             lock_wait: float = 1800.0, lock_ttl: float = 3600.0,
             infra_patterns=None) -> dict:
    """Run a gate in `root` and write <root>/reviews/evidence/<task>-<name>-<time>.log and .json.

    `command` is an argument list, or one string run through the system shell
    when `shell` is true. `exclusive` names the resources that must not be used
    by another gate at the same time; each is locked (sorted) before the command
    runs and released afterwards. Never overwrites a record. Returns the record
    plus `output`, `log_path` and `record_path`; exit code 124 means timeout,
    127 command not found, 75 a busy exclusive resource (the command did not run).
    """
    if not valid_name(task) or not valid_name(name):
        raise ValueError("--task and --name may only contain letters, digits, '.', '_' and '-'")
    argv: List[str] = [command] if shell else list(command)
    if shell and not isinstance(command, str):
        raise ValueError("a shell gate takes one command string")
    if not argv:
        raise ValueError("gate command missing")

    root = Path(root).resolve()
    if isinstance(exclusive, str):
        resources = [exclusive]
    else:
        resources = list(exclusive or ())
    resources = sorted({str(item) for item in resources})
    shown = " ".join(" ".join(argv).split()) if not shell else " ".join(str(command).split())

    started = _utcnow()
    held: List[str] = []
    warnings: List[str] = []
    lock_wait_s = 0.0
    busy = None
    holder_base = {
        "task": task,
        "slot": slot,
        "harness": "cli",
        "pid": os.getpid(),
        "host": socket.gethostname(),
    }

    def _warning_text() -> Optional[str]:
        return "; ".join(warnings) if warnings else None

    try:
        for resource in resources:
            outcome = acquire_lock(
                root, resource, dict(holder_base, started=_utcnow().isoformat(timespec="seconds")),
                wait=lock_wait, ttl=lock_ttl)
            lock_wait_s += float(outcome.get("waited") or 0.0)
            if outcome.get("warning"):
                warnings.append(str(outcome["warning"]))
            if not outcome.get("acquired"):
                busy = (resource, outcome.get("holder"))
                break
            held.append(resource)

        if busy is not None:
            resource, holder = busy
            output = "".join(f"[gate.py] warning: {warning}\n" for warning in warnings)
            output += _busy_line(resource, holder) + "\n"
            result = write_record(
                task, name, root, command=shown, exit_code=BUSY_EXIT, output=output,
                result="busy", slot=slot, exclusive=held,
                lock_wait_s=round(lock_wait_s, 3), started=started, finished=_utcnow(),
                lock_warning=_warning_text())
            result["busy_resource"] = resource
            result["busy_holder"] = holder
            return result

        try:
            outcome = subprocess.run(
                shown if shell else argv, cwd=root, capture_output=True, text=True,
                timeout=timeout, check=False, shell=shell,
            )
            code = outcome.returncode
            output = (outcome.stdout or "") + (outcome.stderr or "")
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            code = 124
            output = ((exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""))
            output += f"\n[gate.py] stopped after {timeout}s\n"
            timed_out = True
        except FileNotFoundError:
            code = 127
            output = f"[gate.py] command not found: {argv[0]}\n"
            timed_out = False

        result_name = classify(code, output, infra_patterns, timed_out=timed_out)
        if warnings:
            output = "".join(f"[gate.py] warning: {warning}\n" for warning in warnings) + output
        return write_record(
            task, name, root, command=shown, exit_code=code, output=output,
            result=result_name, slot=slot, exclusive=held,
            lock_wait_s=round(lock_wait_s, 3), started=started, finished=_utcnow(),
            lock_warning=_warning_text())
    finally:
        for resource in reversed(held):
            release_lock(root, resource)


def summary(result: dict, tail: int = 15, max_errors: int = 15) -> List[str]:
    """Short report of a run_gate() result: one line on success, error and last lines on failure.
    A busy run gets one BUSY line; the last line is always `record: <path>`."""
    root = result["root"]
    rel = result["log_path"].relative_to(root)
    rel_record = result["record_path"].relative_to(root).as_posix()
    lines = result["output"].splitlines()
    name, code = result["gate"], result["exit_code"]

    if result.get("result") == "busy":
        resource = result.get("busy_resource") or "resource"
        return [
            f"GATE {name}: BUSY (exit {code}) — {resource} held by "
            f"{_holder_text(result.get('busy_holder'))}; rerun alone",
            f"record: {rel_record}",
        ]

    if code == 0:
        return [f"GATE {name}: PASS (exit 0) — {len(lines)} lines in {rel}", f"record: {rel_record}"]

    out = [f"GATE {name}: FAIL (exit {code}) — {result['command']}"]
    errors = [line for line in lines if ERROR_LINE.search(line)]
    if errors:
        out.append(f"-- first {min(len(errors), max_errors)} of {len(errors)} error lines")
        out += [line[:300] for line in errors[:max_errors]]
    out.append(f"-- last {min(len(lines), tail)} lines")
    out += [line[:300] for line in lines[-tail:]]
    out.append(f"-- full output: {rel}")
    out.append(f"record: {rel_record}")
    return out
