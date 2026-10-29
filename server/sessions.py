"""Headless agent sessions for the dashboard (2.0).

A session is one non-interactive agent run for one task: the dashboard composes
the prompt from the task brief and the role, spawns the configured provider
(Claude Code by default) in the project or a task worktree, streams the
provider's JSON events into a transcript and records the token use in
``runs/<ID>.json`` when the provider reports it.

The agent stays inside the Polier rules: the generated Claude settings file
installs the shipped hooks (``adapters/claude-code/hook.py``) with
``POLIER_ROLE``/``POLIER_TASK`` in the environment, so a write outside the
task's scope is denied even in a headless run.

Nothing here is required for the CLI workflow; without a provider the dashboard
only reads the project.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from core import board as board_mod
from core import claims as claims_mod
from core import runs as runs_mod
from core import runtime as runtime_mod
from core.errors import PolierError

DEFAULT_SESSION = {
    "provider": "claude",
    "command": ["claude"],
    "permission_mode": "acceptEdits",
    "allowed_tools": ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "TodoWrite"],
    "model": None,
    "timeout_s": 7200,
    "max_concurrent": 2,
    "env": {},
}
ROLES = ("worker", "reviewer", "lead", "generator")
MAX_LOG_LINES = 5000


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _tail(text: str, limit: int = 300) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class Session:
    def __init__(self, session_id: str, task: Optional[str], role: str, folder: Path) -> None:
        self.id = session_id
        self.task = task
        self.role = role
        self.folder = folder
        self.status = "starting"
        self.started = _now()
        self.ended: Optional[str] = None
        self.exit_code: Optional[int] = None
        self.error: Optional[str] = None
        self.process: Optional[subprocess.Popen] = None
        self.tokens = 0
        self.cost: Optional[float] = None
        self.worktree: Optional[str] = None
        self.provider = "claude"
        self.model: Optional[str] = None
        self.prompt = ""
        self.transcript = folder / "transcript.jsonl"
        self.log_path = folder / "session.log"
        self.meta_path = folder / "meta.json"
        self.lock = threading.Lock()
        self.lines: List[str] = []
        self.usages: Dict[str, Any] = {}
        self.last_message: Optional[str] = None
        self.claimed = False
        self.stopped = threading.Event()

    def log(self, text: str) -> None:
        text = text.rstrip("\n")
        with self.lock:
            self.lines.append(text)
            if len(self.lines) > MAX_LOG_LINES:
                del self.lines[: len(self.lines) - MAX_LOG_LINES]
        runtime_mod.append_line(self.log_path, text)

    def transcript_line(self, raw: str) -> None:
        runtime_mod.append_line(self.transcript, raw)

    def view(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "id": self.id,
                "task": self.task,
                "role": self.role,
                "status": self.status,
                "provider": self.provider,
                "model": self.model,
                "started": self.started,
                "ended": self.ended,
                "exit_code": self.exit_code,
                "error": self.error,
                "tokens": self.tokens,
                "cost_usd": self.cost,
                "worktree": self.worktree,
                "folder": str(self.folder),
                "transcript": str(self.transcript),
                "prompt": self.prompt,
                "claimed": self.claimed,
                "last_message": self.last_message,
                "lines": list(self.lines[-200:]),
            }

    def save_meta(self) -> None:
        runtime_mod.write_json(self.meta_path, self.view())


class SessionManager:
    """Owns the headless sessions of one project."""

    def __init__(self, root, bus, config: Optional[Dict[str, Any]] = None,
                 package_root: Optional[Path] = None) -> None:
        self.root = Path(root).resolve()
        self.bus = bus
        self.package_root = Path(package_root) if package_root else Path(__file__).resolve().parents[1]
        self.config = {**DEFAULT_SESSION, **(config or {})}
        self.folder = runtime_mod.sub(self.root, "sessions")
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.Lock()

    # -- configuration -----------------------------------------------------
    def settings(self) -> Dict[str, Any]:
        return dict(self.config)

    def update_settings(self, values: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(values, dict):
            raise PolierError("session settings must be an object")
        allowed = set(DEFAULT_SESSION)
        for key in values:
            if key not in allowed:
                raise PolierError(f"unknown session setting '{key}'")
        for key in ("provider", "permission_mode", "model", "timeout_s", "max_concurrent"):
            if key in values and values[key] is not None and not isinstance(values[key], (str, int)):
                raise PolierError(f"{key} has the wrong type")
        if "command" in values:
            command = values["command"]
            if not isinstance(command, list) or not command or any(not isinstance(part, str) for part in command):
                raise PolierError("command must be a non-empty list of strings")
        if "allowed_tools" in values and not isinstance(values["allowed_tools"], list):
            raise PolierError("allowed_tools must be a list")
        self.config.update({key: value for key, value in values.items()})
        return self.settings()

    # -- lookups -----------------------------------------------------------
    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            sessions = list(self._sessions.values())
        sessions.sort(key=lambda session: session.started, reverse=True)
        return [session.view() for session in sessions]

    def get(self, session_id: str) -> Dict[str, Any]:
        return self._session(session_id).view()

    def log(self, session_id: str, offset: int = 0, limit: int = 262_144) -> Dict[str, Any]:
        session = self._session(session_id)
        offset = max(0, int(offset))
        try:
            size = session.log_path.stat().st_size
        except OSError:
            size = 0
        text = ""
        next_offset = offset
        if offset < size:
            with session.log_path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(offset)
                text = handle.read(max(1024, int(limit)))
                next_offset = offset + len(text.encode("utf-8"))
        return {"id": session.id, "offset": offset, "next": next_offset, "size": size, "text": text}

    def stop(self, session_id: str) -> Dict[str, Any]:
        session = self._session(session_id)
        session.stopped.set()
        process = session.process
        if process and process.poll() is None:
            _terminate(process)
        session.log("[dashboard] stop requested")
        return session.view()

    # -- start -------------------------------------------------------------
    def start(self, *, task: Optional[str] = None, role: str = "worker",
              prompt: Optional[str] = None, note: Optional[str] = None,
              worktree: bool = False, model: Optional[str] = None,
              extra_env: Optional[Dict[str, str]] = None,
              label: Optional[str] = None) -> Dict[str, Any]:
        role = (role or "worker").strip()
        if role not in ROLES:
            raise PolierError(f"role must be one of {', '.join(ROLES)}")
        board = board_mod.load_board(self.root, strict=False)
        if board is None and (role != "generator" or not prompt):
            raise PolierError("no board.json; plan the project first (a generator session needs a prompt)")
        if task is not None:
            if board is None:
                raise PolierError("no board.json; a task session needs a plan")
            task = task.strip()
            if not any(isinstance(entry, dict) and entry.get("id") == task for entry in board.get("tasks", [])):
                raise PolierError(f"unknown task {task}")
        with self._lock:
            running = [session for session in self._sessions.values() if session.status in ("starting", "running")]
            if len(running) >= int(self.config.get("max_concurrent") or 2):
                raise PolierError(f"already {len(running)} session(s) running (max_concurrent)")
            for session in running:
                if task and session.task == task:
                    raise PolierError(f"task {task} already has a running session ({session.id})")
            session_id = f"s-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
            folder = self.folder / session_id
            folder.mkdir(parents=True, exist_ok=True)
            session = Session(session_id, task, role, folder)
            session.provider = str(self.config.get("provider") or "claude")
            session.model = model or self.config.get("model")
            self._sessions[session_id] = session
        prompt_text = prompt if prompt is not None else self._compose_prompt(board or {}, task, role, note)
        session.prompt = prompt_text
        runtime_mod.write_text(session.folder / "prompt.md", prompt_text)
        session.save_meta()
        self._publish(session)
        thread = threading.Thread(target=self._run, args=(session, worktree, extra_env), daemon=True)
        thread.start()
        return session.view()

    def _session(self, session_id: str) -> Session:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(session_id)
        return session

    def _publish(self, session: Session) -> None:
        if self.bus is not None:
            self.bus.publish("session", session.view())

    # -- prompt ------------------------------------------------------------
    def _task(self, board: dict, task_id: str) -> dict:
        return next(entry for entry in board.get("tasks", []) if isinstance(entry, dict)
                    and entry.get("id") == task_id)

    def _compose_prompt(self, board: dict, task_id: Optional[str], role: str,
                        note: Optional[str]) -> str:
        project = board.get("project") or "this project"
        base_branch = board.get("base_branch") or "main"
        parts: List[str] = [
            f"You are a Polier {role} session for the project '{project}'.",
            "",
            "Work autonomously in the current working directory. Do not ask questions. "
            "Follow AGENTS.md and the project rules; the Polier dashboard is watching this session.",
        ]
        if task_id:
            task = self._task(board, task_id)
            parts += [
                "",
                f"## Task {task_id}: {task.get('title', '')}",
                "",
                f"Goal: {task.get('goal', '')}",
                "",
                "Scope (write only inside these paths):",
                *[f"- {entry}" for entry in (task.get("scope_write") or [])],
                "",
                "Gates: " + ", ".join(task.get("gates") or []),
                "Acceptance: " + ", ".join(task.get("acceptance") or []),
                "",
                f"The full brief is at tasks/{task_id}.md; read it first, together with "
                "AGENTS.md, ARCHITECTURE.md and STATUS.md.",
            ]
            if role == "worker":
                parts += [
                    "",
                    "Implement the task. Run the gates with tools/gate.py as the brief says "
                    "(the dashboard can run them too). Do not change board status; the lead does that.",
                ]
            elif role == "reviewer":
                parts += [
                    "",
                    f"Review the work for {task_id}: the diff, acceptance and gate records. "
                    f"Write reviews/{task_id}.md with a plain 'verdict: pass' or 'verdict: fail' line "
                    "and concrete findings.",
                ]
            elif role == "lead":
                parts += [
                    "",
                    "You are the lead: coordinate the task, run gates through tools/gate.py, "
                    "and change status only through tools/state.py set.",
                ]
        if note:
            parts += ["", "## Operator note", note.strip()]
        return "\n".join(parts).strip() + "\n"

    # -- execution ---------------------------------------------------------
    def _run(self, session: Session, worktree: bool, extra_env: Optional[Dict[str, str]]) -> None:
        try:
            cwd = self.root
            if worktree and session.task:
                cwd = self._start_worktree(session)
                session.worktree = str(cwd)
            session.status = "running"
            session.save_meta()
            self._publish(session)
            if session.task:
                try:
                    claims_mod.take(self.root, session.task, harness="claude-code",
                                    session=session.id, worktree=str(cwd))
                    session.claimed = True
                except claims_mod.ClaimConflict as exc:
                    session.log(f"[dashboard] claim not taken: {exc}")
            settings = self._write_settings(session, cwd) if str(self.config.get("provider") or "claude") == "claude" else None
            argv = self._argv(session, settings)
            env = self._env(session, cwd, extra_env)
            session.log(f"$ {' '.join(argv)}")
            process = subprocess.Popen(
                argv, cwd=str(cwd), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, **_process_group_kwargs())
            session.process = process
            self._publish(session)
            assert process.stdout is not None
            deadline = time.time() + int(self.config.get("timeout_s") or 7200)
            for line in process.stdout:
                session.transcript_line(line)
                self._handle_line(session, line)
                if session.stopped.is_set():
                    _terminate(process)
                    break
                if time.time() > deadline:
                    session.log(f"[dashboard] session stopped after {self.config.get('timeout_s')}s")
                    _terminate(process)
                    session.error = "timeout"
                    break
            code = process.wait()
            session.exit_code = code
            stopped = session.stopped.is_set()
            if stopped:
                session.status = "stopped"
            elif code == 0:
                session.status = "done"
            else:
                session.status = "failed"
            if session.tokens:
                try:
                    runs_mod.record_usage(self.root, session.task, session.tokens,
                                          session=session.id, source=session.provider)
                except Exception as exc:  # noqa: BLE001 - usage must not break a session
                    session.log(f"[dashboard] usage not recorded: {exc}")
            session.log(f"[dashboard] session {session.status} (exit {code})"
                        + (f", {session.tokens} tokens" if session.tokens else ""))
        except Exception as exc:  # noqa: BLE001 - report, never crash the server
            session.status = "failed"
            session.error = str(exc)
            session.log(f"[dashboard] session error: {exc}")
        finally:
            # Release the claim before the final publish: a reader that sees the
            # session finished must not still see the claim as held.
            if session.claimed and session.task:
                try:
                    claims_mod.release(self.root, session.task, session.id)
                except Exception:  # noqa: BLE001
                    pass
            session.ended = _now()
            session.save_meta()
            self._publish(session)

    def _start_worktree(self, session: Session) -> Path:
        script = self.package_root / "tools" / "worktree.py"
        board = board_mod.load_board(self.root, strict=False) or {}
        base = board.get("base_branch") or "main"
        result = subprocess.run(
            [sys.executable, str(script), "start", str(session.task), "--root", str(self.root),
             "--base", str(base), "--session", session.id, "--harness", "claude-code"],
            capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise PolierError(f"worktree start failed: {(result.stderr or result.stdout).strip()}")
        lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
        if not lines:
            raise PolierError("worktree start printed no path")
        path = Path(lines[-1])
        if not path.is_dir():
            raise PolierError(f"worktree path does not exist: {path}")
        session.log(f"[dashboard] worktree: {path}")
        return path

    def _argv(self, session: Session, settings: Optional[Path]) -> List[str]:
        command = list(self.config.get("command") or ["claude"])
        provider = str(self.config.get("provider") or "claude")
        if provider != "claude":
            # A custom provider is a plain command list; the prompt is its last argument.
            return command + [session.prompt]
        if command and command[0] == "claude" and not shutil.which("claude"):
            raise PolierError("the 'claude' command was not found in PATH")
        argv = command + ["-p", "--output-format", "stream-json", "--verbose"]
        mode = self.config.get("permission_mode")
        if mode:
            argv += ["--permission-mode", str(mode)]
        tools = self.config.get("allowed_tools")
        if isinstance(tools, list) and tools:
            argv += ["--allowedTools", " ".join(str(tool) for tool in tools)]
        if session.model:
            argv += ["--model", str(session.model)]
        if settings is not None:
            argv += ["--settings", str(settings)]
        if self.config.get("append_system_prompt"):
            argv += ["--append-system-prompt", str(self.config["append_system_prompt"])]
        argv.append(session.prompt)
        return argv

    def _env(self, session: Session, cwd: Path, extra_env: Optional[Dict[str, str]]) -> Dict[str, str]:
        env = dict(os.environ)
        env.update({str(key): str(value) for key, value in (self.config.get("env") or {}).items()})
        env.update({
            "POLIER_ROLE": session.role if session.role in ("lead", "reviewer") else "worker",
            "POLIER_ENFORCE": "deny",
            "POLIER_STOP_CHECK": "1",
            "POLIER_USAGE": "0",
            "POLIER_DASHBOARD_SESSION": session.id,
            "POLIER_PROJECT_ROOT": str(self.root),
        })
        if session.task:
            env["POLIER_TASK"] = session.task
        if extra_env:
            env.update({str(key): str(value) for key, value in extra_env.items()})
        return env

    def _write_settings(self, session: Session, cwd: Path) -> Optional[Path]:
        hook = self.package_root / "adapters" / "claude-code" / "hook.py"
        if not hook.is_file():
            return None
        settings = {
            "hooks": {
                "PreToolUse": [{
                    "matcher": "Write|Edit|MultiEdit|NotebookEdit|Bash",
                    "hooks": [{"type": "command",
                               "command": f'"{sys.executable}" "{hook}" pre-tool-use',
                               "timeout": 30}],
                }],
                "Stop": [{
                    "hooks": [{"type": "command",
                               "command": f'"{sys.executable}" "{hook}" stop',
                               "timeout": 120}],
                }],
            }
        }
        path = session.folder / "settings.json"
        runtime_mod.write_json(path, settings)
        return path

    # -- provider output ---------------------------------------------------
    def _handle_line(self, session: Session, line: str) -> None:
        text = line.strip()
        if not text:
            return
        try:
            event = json.loads(text)
        except ValueError:
            session.log(text[:2000])
            return
        if not isinstance(event, dict):
            session.log(text[:2000])
            return
        kind = event.get("type")
        if kind == "system":
            subtype = event.get("subtype") or ""
            session.log(f"[system] {subtype} {event.get('model') or ''}".strip())
            return
        if kind == "assistant":
            message = event.get("message") or {}
            for block in message.get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and block.get("text"):
                    session.last_message = str(block.get("text"))
                    for piece in str(block["text"]).splitlines():
                        session.log(piece)
                elif block.get("type") == "tool_use":
                    session.log(f"[tool] {block.get('name')}: {_tail(json.dumps(block.get('input') or {}))}")
            return
        if kind == "user":
            message = event.get("message") or {}
            for block in message.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    content = block.get("content")
                    if isinstance(content, list):
                        text_parts = [str(part.get("text", "")) for part in content if isinstance(part, dict)]
                        content = " ".join(text_parts)
                    session.log(f"[result] {_tail(content)}")
            return
        if kind == "result":
            subtype = event.get("subtype")
            usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
            tokens = 0
            for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens"):
                value = usage.get(key)
                if isinstance(value, (int, float)):
                    tokens += int(value)
            session.usages = usage
            session.tokens += tokens
            if isinstance(event.get("total_cost_usd"), (int, float)):
                session.cost = float(event["total_cost_usd"])
            message = event.get("result")
            if message:
                session.last_message = str(message)
                for piece in str(message).splitlines():
                    session.log(piece)
            flag = "ok" if subtype == "success" and not event.get("is_error") else "error"
            session.log(f"[result] {flag}{f', {tokens} tokens' if tokens else ''}")
            if event.get("is_error"):
                session.error = str(message or subtype or "provider reported an error")
            return
        session.log(f"[{kind or 'event'}] {_tail(json.dumps(event))}")


def _process_group_kwargs() -> Dict[str, Any]:
    return {"start_new_session": True} if os.name == "posix" else {}


def _terminate(process: subprocess.Popen) -> None:
    import signal

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
            pass
