"""Background jobs: streaming gate runs, project checks and audits (2.0).

The CLI stays the reference implementation; a dashboard job runs the same
command and writes the same records:

- a gate uses ``core.gate.write_record`` and ``core.runs.record_gate`` exactly
  like ``tools/gate.py``, after streaming the command output live;
- ``check`` runs ``tools/check.py``;
- ``audit`` calls ``core.audit.audit`` and returns its JSON.

Jobs run in a thread with a child process; stopping a job signals the process
group. Output is kept in a log file under the dashboard runtime folder and read
back by byte offset, so a long build never grows the JSON response.
"""
from __future__ import annotations

import datetime as dt
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import board as board_mod
from . import gate as gate_mod
from . import locks
from . import policy as policy_mod
from . import runs as runs_mod
from . import runtime as runtime_mod
from .errors import PolierError

MAX_LINE = 4000
MAX_LOG_BYTES = 8 * 1024 * 1024
TAIL_LINES = 400


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _command_text(command: Any) -> str:
    if isinstance(command, str):
        return " ".join(command.split())
    return " ".join(str(part) for part in command)


class Job:
    """One background run. Plain dicts in and out; never touch it from outside."""

    def __init__(self, job_id: str, kind: str, label: str, log_path: Path) -> None:
        self.id = job_id
        self.kind = kind
        self.label = label
        self.status = "running"
        self.created = _now()
        self.started = self.created
        self.ended: Optional[str] = None
        self.exit_code: Optional[int] = None
        self.error: Optional[str] = None
        self.result: Optional[Dict[str, Any]] = None
        self.log_path = log_path
        self.command: str = ""
        self.meta: Dict[str, Any] = {}
        self.process: Optional[subprocess.Popen] = None
        self.pid: Optional[int] = None
        self.stopped = threading.Event()
        self.bytes = 0
        self.tail: List[str] = []
        self.lock = threading.Lock()

    def view(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "id": self.id,
                "kind": self.kind,
                "label": self.label,
                "status": self.status,
                "created": self.created,
                "started": self.started,
                "ended": self.ended,
                "exit_code": self.exit_code,
                "error": self.error,
                "result": self.result,
                "command": self.command,
                "meta": self.meta,
                "bytes": self.bytes,
                "pid": self.pid,
                "log": str(self.log_path),
                "tail": list(self.tail[-40:]),
            }


def _append(job: Job, line: str, bus=None) -> None:
    line = line.rstrip("\n")
    if len(line) > MAX_LINE:
        line = line[:MAX_LINE] + " …"
    with job.lock:
        if job.bytes < MAX_LOG_BYTES:
            try:
                with job.log_path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
                    job.bytes += len((line + "\n").encode("utf-8"))
            except OSError:
                pass
        job.tail.append(line)
        if len(job.tail) > TAIL_LINES:
            del job.tail[: len(job.tail) - TAIL_LINES]


class JobManager:
    """Thread-safe registry of running and finished jobs."""

    def __init__(self, root: Path, bus=None, package_root: Optional[Path] = None) -> None:
        self.root = Path(root).resolve()
        self.bus = bus
        self.package_root = Path(package_root) if package_root else Path(__file__).resolve().parents[1]
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        self._folder = runtime_mod.sub(self.root, "jobs")

    # -- lookups -----------------------------------------------------------
    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda job: job.started, reverse=True)
        return [job.view() for job in jobs]

    def get(self, job_id: str) -> Dict[str, Any]:
        job = self._job(job_id)
        return job.view()

    def log(self, job_id: str, offset: int = 0, limit: int = 262_144) -> Dict[str, Any]:
        job = self._job(job_id)
        offset = max(0, int(offset))
        try:
            size = job.log_path.stat().st_size
        except OSError:
            size = 0
        text = ""
        next_offset = offset
        if offset < size:
            with job.log_path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(offset)
                text = handle.read(max(1024, int(limit)))
                next_offset = offset + len(text.encode("utf-8"))
        return {"id": job.id, "offset": offset, "next": next_offset, "size": size,
                "text": text, "status": job.status}

    def stop(self, job_id: str) -> Dict[str, Any]:
        job = self._job(job_id)
        job.stopped.set()
        process = job.process
        if process and process.poll() is None:
            _terminate(process)
        return job.view()

    # -- internals ---------------------------------------------------------
    def _job(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def _new(self, kind: str, label: str) -> Job:
        job_id = f"{kind}-{time.strftime('%H%M%S')}-{uuid.uuid4().hex[:6]}"
        job = Job(job_id, kind, label, self._folder / f"{job_id}.log")
        job.log_path.write_text("", encoding="utf-8")
        with self._lock:
            self._jobs[job_id] = job
        self._publish(job)
        return job

    def _publish(self, job: Job) -> None:
        if self.bus is not None:
            self.bus.publish("job", job.view())

    def _finish(self, job: Job, status: str, *, exit_code: Optional[int] = None,
                error: Optional[str] = None, result: Optional[Dict[str, Any]] = None) -> None:
        with job.lock:
            job.status = status
            job.exit_code = exit_code
            job.error = error
            job.result = result
            job.ended = _now()
        self._publish(job)

    # -- gates -------------------------------------------------------------
    def start_gate(self, task_id: str, name: str, command: str, *, shell: bool = True,
                   timeout: int = 1800, slot: Optional[int] = None) -> Dict[str, Any]:
        task_id, name = str(task_id).strip(), str(name).strip()
        if not gate_mod.valid_name(task_id) or not gate_mod.valid_name(name):
            raise PolierError("task and gate names may only contain letters, digits, '.', '_' and '-'")
        command = (command or "").strip()
        if not command:
            raise PolierError("gate command missing")
        job = self._new("gate", f"{name} · {task_id}")
        job.command = " ".join(command.split())
        job.meta = {"task": task_id, "gate": name}
        thread = threading.Thread(target=self._run_gate, args=(job, command, shell, timeout, slot), daemon=True)
        thread.start()
        return job.view()

    def _run_gate(self, job: Job, command: str, shell: bool, timeout: int, slot: Optional[int]) -> None:
        root = self.root
        task_id = str(job.meta["task"])
        name = str(job.meta["gate"])
        exclusive: List[str] = []
        infra_patterns: List[str] = []
        board = board_mod.load_board(root, strict=False)
        if board is not None:
            for entry in board.get("tasks") or []:
                if isinstance(entry, dict) and entry.get("id") == task_id:
                    values = entry.get("exclusive")
                    if isinstance(values, list):
                        exclusive = [value for value in values if isinstance(value, str)]
                    break
            infra_patterns = list(board_mod.resources(board)["infra_patterns"])
        held: List[str] = []
        warnings: List[str] = []
        waited = 0.0
        started = gate_mod._utcnow()
        try:
            for resource in sorted({str(item) for item in exclusive}):
                outcome = locks.acquire_lock(
                    root, resource,
                    {"task": task_id, "slot": slot, "harness": "dashboard", "pid": os.getpid(),
                     "host": os.uname().nodename if hasattr(os, "uname") else "",
                     "started": _now()},
                    wait=1800.0, ttl=3600.0)
                waited += float(outcome.get("waited") or 0.0)
                if outcome.get("warning"):
                    warnings.append(str(outcome["warning"]))
                if not outcome.get("acquired"):
                    output = "".join(f"[dashboard] warning: {warning}\n" for warning in warnings)
                    output += f"[dashboard] busy: resource {resource} is held by {outcome.get('holder')}\n"
                    _append(job, output, self.bus)
                    record = gate_mod.write_record(
                        task_id, name, root, command=job.command, exit_code=gate_mod.BUSY_EXIT,
                        output=output, result="busy", slot=slot, exclusive=held,
                        lock_wait_s=round(waited, 3), started=started, finished=gate_mod._utcnow(),
                        lock_warning="; ".join(warnings) or None)
                    self._record(job, record, "busy")
                    return
                held.append(resource)
            if warnings:
                for warning in warnings:
                    _append(job, f"[dashboard] warning: {warning}", self.bus)
            process = subprocess.Popen(
                command if shell else command.split(), cwd=str(root), shell=shell,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                **_process_group_kwargs())
            job.process = process
            job.pid = process.pid
            if job.stopped.is_set():
                _terminate(process)
            deadline = time.time() + max(1, int(timeout))
            timed_out = False
            output_parts: List[str] = []
            output_bytes = 0
            assert process.stdout is not None
            for line in process.stdout:
                _append(job, line, self.bus)
                if output_bytes < MAX_LOG_BYTES:
                    output_parts.append(line)
                    output_bytes += len(line.encode("utf-8"))
                if job.stopped.is_set():
                    _terminate(process)
                    break
                if time.time() > deadline:
                    timed_out = True
                    _terminate(process)
                    break
            code = process.wait()
            if timed_out:
                code = 124
                _append(job, f"[dashboard] stopped after {timeout}s", self.bus)
            output = "".join(output_parts)
            result_name = gate_mod.classify(code, output, infra_patterns, timed_out=timed_out)
            if job.stopped.is_set() and not timed_out:
                result_name = "fail"
                _append(job, "[dashboard] stopped by the operator", self.bus)
            record = gate_mod.write_record(
                task_id, name, root, command=job.command, exit_code=code, output=output,
                result=result_name, slot=slot, exclusive=held,
                lock_wait_s=round(waited, 3), started=started, finished=gate_mod._utcnow(),
                lock_warning="; ".join(warnings) or None)
            self._record(job, record, result_name)
        except Exception as exc:  # noqa: BLE001 - a job must report, never crash the server
            _append(job, f"[dashboard] error: {exc}", self.bus)
            self._finish(job, "error", error=str(exc))
        finally:
            for resource in reversed(held):
                try:
                    locks.release_lock(root, resource)
                except Exception:  # noqa: BLE001
                    pass

    def _record(self, job: Job, record: Dict[str, Any], result_name: str) -> None:
        root = self.root
        task_id, name = str(job.meta["task"]), str(job.meta["gate"])
        record_rel = None
        try:
            record_rel = record["record_path"].relative_to(record["root"]).as_posix()
        except Exception:  # noqa: BLE001
            pass
        if runs_mod.enabled(root):
            try:
                runs_mod.record_gate(root, task_id, name, result_name, record_rel)
            except Exception:  # noqa: BLE001 - a gate must not fail because of its run record
                pass
        took = _duration(job.started)
        _append(job, f"[dashboard] gate {name} {result_name} (exit {record.get('exit_code')}) in {took}s", self.bus)
        self._finish(job, "pass" if result_name == "pass" else "fail",
                     exit_code=int(record.get("exit_code") or 0),
                     result={"gate": name, "task": task_id, "outcome": result_name,
                             "record": record_rel, "log": f"reviews/evidence/{record.get('log')}",
                             "duration_s": took})

    # -- checks and audits -------------------------------------------------
    def start_check(self) -> Dict[str, Any]:
        job = self._new("check", "board check")
        thread = threading.Thread(target=self._run_check, args=(job,), daemon=True)
        thread.start()
        return job.view()

    def _run_check(self, job: Job) -> None:
        script = self.package_root / "tools" / "check.py"
        argv = [sys.executable, str(script), str(self.root)]
        job.command = " ".join(argv)
        self._run_stream(job, argv)

    def start_audit(self) -> Dict[str, Any]:
        job = self._new("audit", "audit")
        thread = threading.Thread(target=self._run_audit, args=(job,), daemon=True)
        thread.start()
        return job.view()

    def _run_audit(self, job: Job) -> None:
        from . import audit as audit_mod

        job.command = "core.audit.audit"
        try:
            result = audit_mod.audit(self.root)
            for finding in result.get("tasks", []):
                if isinstance(finding, dict):
                    line = f"{finding.get('task')}: {finding.get('status')}"
                    for error in finding.get("errors", []) or []:
                        line += f" | error: {error}"
                    for warning in finding.get("warnings", []) or []:
                        line += f" | warning: {warning}"
                    _append(job, line, self.bus)
            for line in result.get("findings", []) or []:
                if isinstance(line, dict):
                    _append(job, f"{line.get('task')}: {line.get('kind')} {line.get('message')}", self.bus)
            errors = int(result.get("errors") or 0)
            _append(job, f"[audit] {errors} error(s), {result.get('warnings', 0)} warning(s)", self.bus)
            self._finish(job, "pass" if errors == 0 else "fail", exit_code=0 if errors == 0 else 1,
                         result={"errors": errors, "warnings": result.get("warnings", 0)})
        except Exception as exc:  # noqa: BLE001
            _append(job, f"[audit] error: {exc}", self.bus)
            self._finish(job, "error", error=str(exc))

    def _run_stream(self, job: Job, argv: List[str]) -> None:
        try:
            process = subprocess.Popen(argv, cwd=str(self.root), stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, bufsize=1,
                                       **_process_group_kwargs())
            job.process = process
            assert process.stdout is not None
            for line in process.stdout:
                _append(job, line, self.bus)
            code = process.wait()
            self._finish(job, "pass" if code == 0 else "fail", exit_code=code)
        except Exception as exc:  # noqa: BLE001
            _append(job, f"[dashboard] error: {exc}", self.bus)
            self._finish(job, "error", error=str(exc))


def _process_group_kwargs() -> Dict[str, Any]:
    """Run children in their own process group on POSIX so stop() can signal the tree."""
    return {"start_new_session": True} if os.name == "posix" else {}


def _duration(started: str) -> str:
    try:
        begun = dt.datetime.fromisoformat(started)
        return f"{(dt.datetime.now(dt.timezone.utc) - begun).total_seconds():.1f}"
    except ValueError:
        return "?"


def _terminate(process: subprocess.Popen) -> None:
    """Stop the whole process group of a job (shell commands spawn children)."""
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        else:
            process.terminate()
    except (ProcessLookupError, PermissionError, OSError):
        try:
            process.terminate()
        except OSError:
            pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "posix":
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            else:
                process.kill()
        except (ProcessLookupError, PermissionError, OSError):
            try:
                process.kill()
            except OSError:
                pass
