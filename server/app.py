"""The local dashboard server (2.0): HTTP + Server-Sent Events, standard library only.

Run it with ``python3 tools/serve.py [project]``. It binds to ``127.0.0.1`` by
default and speaks one small JSON API plus a self-contained web UI (see
``server/assets``). Nothing here is required for the CLI workflow: every action
goes through the same ``core`` functions the CLI uses, so the files stay the
source of truth.

Security model
--------------
- loopback only unless the operator passes ``--host`` together with ``--token``;
- optional bearer token (``--token`` or ``POLIER_DASHBOARD_TOKEN``), also
  accepted as ``?token=`` and then set as an HttpOnly cookie for the UI;
- state-changing requests need the ``X-Polier-Action: 1`` header (a plain form
  or a cross-site request cannot set it);
- ``--read-only`` (or ``--role viewer``) refuses every write;
- the first write in a session must come from the same origin as the page.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import socket
import threading
import time
import traceback
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from core import analytics as analytics_mod
from core import approvals as approvals_mod
from core import audit as audit_mod
from core import board as board_mod
from core import claims as claims_mod
from core import coverage as coverage_mod
from core import cycles as cycles_mod
from core import dashboard as dashboard_mod
from core import filters as filters_mod
from core import inbox as inbox_mod
from core import intake as intake_mod
from core import modules as modules_mod
from core import pages as pages_mod
from core import plans as plans_mod
from core import plan_edit
from core import policy as policy_mod
from core import runtime as runtime_mod
from core import settings as settings_mod
from core import state as state_mod
from core import task_templates as templates_mod
from core import timeline as timeline_mod
from core import views as views_mod
from core import worklog as worklog_mod
from core.errors import PolierError
from core.gates import suggest_gate_commands
from core.jobs import JobManager

from .sessions import SessionManager

VERSION = "2.3.0"
CONFIG = "config.json"
MAX_BODY = 1_500_000
ASSETS = Path(__file__).resolve().parent / "assets"


def _header(headers, name: str) -> str:
    """Case-insensitive header lookup for keyword-style handlers."""
    try:
        value = headers.get(name)
    except AttributeError:
        value = None
    if value is None:
        for key, candidate in (headers.items() if hasattr(headers, "items") else []):
            if str(key).lower() == name.lower():
                return str(candidate)
        return ""
    return str(value)


class ApiError(Exception):
    def __init__(self, status: int, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details


class DashboardApp:
    """State and routing for one project."""

    def __init__(self, root, *, host: str = "127.0.0.1", port: int = 8765,
                 token: Optional[str] = None, role: str = "lead", read_only: bool = False,
                 package_root: Optional[Path] = None, open_browser: bool = False,
                 quiet: bool = False) -> None:
        self.root = Path(root).resolve()
        self.host = host
        self.port = int(port)
        self.token = token or None
        self.role = "viewer" if (read_only or role == "viewer") else "lead"
        self.read_only = self.role != "lead"
        self.package_root = Path(package_root) if package_root else Path(__file__).resolve().parents[1]
        self.quiet = quiet
        self.open_browser = open_browser
        self.bus = _Bus()
        self.watcher = _Watcher(self)
        self.jobs = JobManager(self.root, self.bus, self.package_root)
        self.sessions = SessionManager(self.root, self.bus, self._config().get("session"), self.package_root)
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_sig: Optional[str] = None
        self._cache_lock = threading.Lock()
        self.started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # -- configuration -----------------------------------------------------
    def _config_path(self) -> Path:
        return runtime_mod.runtime_dir(self.root) / CONFIG

    def _config(self) -> Dict[str, Any]:
        config = runtime_mod.read_json(self._config_path())
        config.setdefault("version", 1)
        config.setdefault("gate_commands", {})
        config.setdefault("session", {})
        config.setdefault("ui", {})
        return config

    def _save_config(self, config: Dict[str, Any]) -> None:
        runtime_mod.write_json(self._config_path(), config)

    def config_view(self) -> Dict[str, Any]:
        config = self._config()
        return {
            "version": VERSION,
            "project_root": str(self.root),
            "board_present": (self.root / "board.json").is_file(),
            "role": self.role,
            "read_only": self.read_only,
            "token_required": bool(self.token),
            "gate_commands": {**suggest_gate_commands(self.root), **config.get("gate_commands", {})},
            "session": self.sessions.settings(),
            "ui": config.get("ui", {}),
            "polier": {"root": str(self.package_root), "version": self.package_version()},
        }

    def package_version(self) -> Optional[str]:
        try:
            return (self.package_root / "VERSION").read_text(encoding="utf-8").strip()
        except OSError:
            return None

    # -- read models -------------------------------------------------------
    def signature(self) -> str:
        parts: List[str] = []
        root = self.root
        for rel in ("board.json", "policy.json", "dashboard.json"):
            parts.append(_stamp(root / rel))
        parts.append(_dir_stamp(root / "views"))
        for folder in ("runs", "tasks", "reviews"):
            parts.append(_dir_stamp(root / folder))
        parts.append(_dir_stamp(root / "reviews" / "evidence"))
        try:
            from core.paths import git_common_dir

            common = git_common_dir(root)
            parts.append(_dir_stamp(common / "polier" / "claims"))
            parts.append(_dir_stamp(common / "polier" / "slots"))
            parts.append(_stamp(common / "HEAD"))
        except PolierError:
            parts.append("no-git")
        return "|".join(parts)

    def snapshot(self, fresh: bool = False) -> Dict[str, Any]:
        signature = self.signature()
        with self._cache_lock:
            if not fresh and self._cache is not None and signature == self._cache_sig:
                return self._cache
        if not (self.root / "board.json").is_file():
            raise ApiError(409, "no board.json yet — start the interview wizard or run the generator")
        value = dashboard_mod.snapshot(self.root)
        value["dashboard"] = {"version": VERSION, "read_only": self.read_only, "role": self.role,
                              "started": self.started, "signature": signature,
                              "config": self.config_view()}
        with self._cache_lock:
            self._cache, self._cache_sig = value, signature
        return value

    def invalidate(self) -> None:
        with self._cache_lock:
            self._cache, self._cache_sig = None, None

    # -- routing -----------------------------------------------------------
    def handle(self, method: str, raw_path: str, body: Optional[bytes],
               headers: Dict[str, str]) -> Tuple[int, str, Any]:
        parsed = urlparse(raw_path)
        path = parsed.path.rstrip("/") or "/"
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        try:
            self._check_auth(method, path, query, headers)
            if path.startswith("/api/"):
                status, payload = self._api(method, path, query, body, headers)
                return status, "application/json; charset=utf-8", payload
            status, content_type, payload = self._static(path)
            return status, content_type, payload
        except ApiError as exc:
            return exc.status, "application/json; charset=utf-8", {"error": exc.message, "details": exc.details}
        except BrokenPipeError:
            raise
        except Exception as exc:  # noqa: BLE001 - every error becomes a JSON response
            traceback.print_exc()
            return 500, "application/json; charset=utf-8", {"error": f"internal error: {exc}"}

    def _check_auth(self, method: str, path: str, query: Dict[str, str], headers: Dict[str, str]) -> None:
        if self.token:
            supplied = ""
            auth = _header(headers, "authorization")
            if auth.lower().startswith("bearer "):
                supplied = auth[7:].strip()
            supplied = supplied or query.get("token") or ""
            cookie = _header(headers, "cookie")
            if not supplied:
                match = re.search(r"(?:^|;\s*)polier_token=([^;]+)", cookie)
                supplied = match.group(1) if match else ""
            if not secrets.compare_digest(supplied, self.token):
                raise ApiError(401, "missing or wrong dashboard token")
        if method != "GET" and method != "HEAD":
            if _header(headers, "x-polier-action").strip() != "1":
                raise ApiError(403, "state-changing requests need the X-Polier-Action: 1 header")
            origin = _header(headers, "origin")
            host = _header(headers, "host")
            if origin and host:
                origin_host = urlparse(origin).netloc
                if origin_host and origin_host != host:
                    raise ApiError(403, "cross-origin action refused")
            if self.read_only:
                raise ApiError(403, "the dashboard runs read-only (--read-only/--role viewer)")
        # DNS-rebinding protection: a non-loopback bind requires a token.
        host_header = _header(headers, "host").rsplit(":", 1)[0].strip("[]")
        if path.startswith("/api/") and host_header not in ("127.0.0.1", "localhost", "::1", self.host):
            if not self.token:
                raise ApiError(403, f"host {host_header!r} is not allowed without a token")

    def _static(self, path: str) -> Tuple[int, str, bytes]:
        if path in ("/", "/index.html"):
            candidate = ASSETS / "index.html"
            content_type = "text/html; charset=utf-8"
        elif path.startswith("/assets/"):
            name = path[len("/assets/"):]
            if not name or "/" in name or name.startswith("."):
                raise ApiError(404, "not found")
            candidate = ASSETS / name
            content_type = {
                ".js": "text/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".svg": "image/svg+xml",
                ".png": "image/png",
                ".woff2": "font/woff2",
            }.get(candidate.suffix, "application/octet-stream")
        elif path == "/favicon.svg":
            candidate = ASSETS / "favicon.svg"
            content_type = "image/svg+xml"
        elif path == "/healthz":
            return 200, "application/json; charset=utf-8", b'{"ok": true}'
        else:
            raise ApiError(404, "not found")
        if not candidate.is_file():
            raise ApiError(404, "not found")
        return 200, content_type, candidate.read_bytes()

    # -- API ---------------------------------------------------------------
    def _api(self, method: str, path: str, query: Dict[str, str], body: Optional[bytes],
             headers: Dict[str, str]) -> Tuple[int, Any]:
        if path == "/api/health":
            return 200, {
                "ok": True, "version": VERSION, "role": self.role,
                "board_present": (self.root / "board.json").is_file(),
                "root": str(self.root), "started": self.started,
                "read_only": self.read_only,
            }
        if path == "/api/config":
            if method == "GET":
                return 200, self.config_view()
            if method in ("PUT", "POST"):
                payload = self._json(body)
                config = self._config()
                gate_commands = payload.get("gate_commands")
                if gate_commands is not None:
                    if not isinstance(gate_commands, dict) or any(
                            not isinstance(key, str) or not isinstance(value, str)
                            for key, value in gate_commands.items()):
                        raise ApiError(400, "gate_commands must be an object of strings")
                    config["gate_commands"] = gate_commands
                if "session" in payload:
                    try:
                        self.sessions.update_settings(payload["session"])
                    except PolierError as exc:
                        raise ApiError(400, str(exc))
                    config["session"] = self.sessions.settings()
                if "ui" in payload and isinstance(payload["ui"], dict):
                    config["ui"] = payload["ui"]
                self._save_config(config)
                return 200, self.config_view()
            raise ApiError(405, "method not allowed")
        if path == "/api/snapshot":
            return 200, self.snapshot(fresh=query.get("fresh") in ("1", "true", "yes"))
        if path == "/api/dispatch":
            if not (self.root / "board.json").is_file():
                raise ApiError(409, "no board.json yet")
            board = board_mod.load_board(self.root)
            policy = policy_mod.load_policy(self.root)
            return 200, self.snapshot().get("dispatch") if board else {}
        if path == "/api/activity":
            limit = int(query.get("limit") or 150)
            return 200, dashboard_mod.activity(self.root, limit)
        if path == "/api/approvals":
            records = approvals_mod.load_all(self.root)
            status = query.get("status")
            if status:
                records = [record for record in records if record.get("status") == status]
            return 200, records
        if path == "/api/approvals/request" and method == "POST":
            payload = self._json(body)
            action = str(payload.get("action") or "").strip()
            if not action:
                raise ApiError(400, "action is required")
            record = approvals_mod.request(self.root, action, payload.get("task"),
                                           by=str(payload.get("by") or self.role),
                                           note=str(payload.get("note") or ""))
            self.bus.publish("approval", record)
            self.invalidate()
            return 200, record
        match = re.fullmatch(r"/api/approvals/([A-Za-z0-9-]+)/(grant|deny)", path)
        if match and method == "POST":
            approval_id, verb = match.group(1), match.group(2)
            payload = self._json(body)
            by = str(payload.get("by") or "owner")
            note = str(payload.get("note") or "")
            record = (approvals_mod.grant if verb == "grant" else approvals_mod.deny)(
                self.root, approval_id, by=by, note=note)
            self.bus.publish("approval", record)
            self.invalidate()
            return 200, record
        if path == "/api/claims":
            return 200, claims_mod.live_claims(self.root)
        match = re.fullmatch(r"/api/tasks/([A-Za-z0-9_.-]+)", path)
        if match and method == "GET":
            task_id = match.group(1)
            try:
                return 200, dashboard_mod.task_detail(self.root, task_id)
            except KeyError:
                raise ApiError(404, f"unknown task {task_id}")
        match = re.fullmatch(r"/api/tasks/([A-Za-z0-9_.-]+)/state", path)
        if match and method == "POST":
            task_id = match.group(1)
            payload = self._json(body)
            status = str(payload.get("status") or "").strip()
            if not status:
                raise ApiError(400, "status is required")
            try:
                result = state_mod.set_status(
                    self.root, task_id, status, actor=str(payload.get("actor") or "lead"),
                    note=payload.get("note"), force=bool(payload.get("force")))
            except state_mod.TransitionBlocked as exc:  # type: ignore[attr-defined]
                raise ApiError(409, "transition refused", {
                    "errors": getattr(exc, "errors", []), "actions": getattr(exc, "actions", []),
                    "detail": str(exc)})
            self.bus.publish("state", {"task": task_id, "status": status, "result": result})
            self.invalidate()
            return 200, {"ok": True, "result": result, "snapshot": self.snapshot(fresh=True)}
        match = re.fullmatch(r"/api/tasks/([A-Za-z0-9_.-]+)/claim", path)
        if match and method == "POST":
            task_id = match.group(1)
            payload = self._json(body)
            try:
                claim = claims_mod.take(
                    self.root, task_id, harness=str(payload.get("harness") or "dashboard"),
                    session=str(payload.get("session") or f"dashboard-{os.getpid()}"),
                    worktree=payload.get("worktree"), slot=payload.get("slot"))
            except claims_mod.ClaimConflict as exc:  # type: ignore[attr-defined]
                raise ApiError(409, f"claim conflict: {exc}")
            self.bus.publish("claim", claim)
            self.invalidate()
            return 200, claim
        if match and method == "DELETE":
            task_id = match.group(1)
            released = claims_mod.release(self.root, task_id)
            self.bus.publish("claim", {"task": task_id, "released": released})
            self.invalidate()
            return 200, {"task": task_id, "released": released}
        match = re.fullmatch(r"/api/tasks/([A-Za-z0-9_.-]+)/logs/([A-Za-z0-9_.-]+\.log)", path)
        if match and method == "GET":
            try:
                return 200, {"log": match.group(2),
                             "text": dashboard_mod.task_log(self.root, match.group(1), match.group(2))}
            except PolierError as exc:
                raise ApiError(404, str(exc))
        # jobs -------------------------------------------------------------
        if path == "/api/jobs" and method == "GET":
            return 200, self.jobs.list()
        if path == "/api/jobs/gate" and method == "POST":
            payload = self._json(body)
            task_id = str(payload.get("task") or "").strip()
            name = str(payload.get("name") or "").strip()
            command = str(payload.get("command") or "").strip()
            if not command:
                command = (self.config_view()["gate_commands"] or {}).get(name, "")
            if not command:
                raise ApiError(400, f"no command configured for gate '{name}'")
            return 200, self.jobs.start_gate(task_id, name, command,
                                             shell=bool(payload.get("shell", True)),
                                             timeout=int(payload.get("timeout") or 1800),
                                             slot=payload.get("slot"))
        if path == "/api/jobs/check" and method == "POST":
            return 200, self.jobs.start_check()
        if path == "/api/jobs/audit" and method == "POST":
            return 200, self.jobs.start_audit()
        match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_.-]+)", path)
        if match and method == "GET":
            try:
                return 200, self.jobs.get(match.group(1))
            except KeyError:
                raise ApiError(404, "unknown job")
        match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_.-]+)/log", path)
        if match and method == "GET":
            try:
                return 200, self.jobs.log(match.group(1), int(query.get("offset") or 0),
                                          int(query.get("limit") or 262144))
            except KeyError:
                raise ApiError(404, "unknown job")
        match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_.-]+)/stop", path)
        if match and method == "POST":
            try:
                return 200, self.jobs.stop(match.group(1))
            except KeyError:
                raise ApiError(404, "unknown job")
        # sessions ---------------------------------------------------------
        if path == "/api/sessions" and method == "GET":
            return 200, self.sessions.list()
        if path == "/api/sessions" and method == "POST":
            payload = self._json(body)
            role = str(payload.get("role") or "worker")
            try:
                session = self.sessions.start(
                    task=payload.get("task") or None, role=role,
                    prompt=payload.get("prompt") or None, note=payload.get("note") or None,
                    worktree=bool(payload.get("worktree")), model=payload.get("model") or None,
                    extra_env=payload.get("env") if isinstance(payload.get("env"), dict) else None)
            except PolierError as exc:
                raise ApiError(400, str(exc))
            self.bus.publish("session", session)
            self.invalidate()
            return 200, session
        match = re.fullmatch(r"/api/sessions/([A-Za-z0-9_.-]+)", path)
        if match and method == "GET":
            try:
                return 200, self.sessions.get(match.group(1))
            except KeyError:
                raise ApiError(404, "unknown session")
        match = re.fullmatch(r"/api/sessions/([A-Za-z0-9_.-]+)/log", path)
        if match and method == "GET":
            try:
                return 200, self.sessions.log(match.group(1), int(query.get("offset") or 0),
                                              int(query.get("limit") or 262144))
            except KeyError:
                raise ApiError(404, "unknown session")
        match = re.fullmatch(r"/api/sessions/([A-Za-z0-9_.-]+)/stop", path)
        if match and method == "POST":
            try:
                session = self.sessions.stop(match.group(1))
            except KeyError:
                raise ApiError(404, "unknown session")
            return 200, session
        # plan / interview -------------------------------------------------
        if path == "/api/plan" and method == "GET":
            draft = plans_mod.status(self.root)
            draft["board_present"] = (self.root / "board.json").is_file()
            draft["gate_commands"] = self.config_view()["gate_commands"]
            return 200, draft
        if path == "/api/plan/answers" and method in ("PUT", "POST"):
            payload = self._json(body)
            try:
                draft = plans_mod.save_answers(self.root, payload.get("answers") or {},
                                               payload.get("mode"))
            except PolierError as exc:
                raise ApiError(400, str(exc))
            self.bus.publish("plan", {"status": draft.get("status")})
            return 200, plans_mod.status(self.root)
        if path == "/api/plan/generator" and method == "POST":
            payload = self._json(body)
            if payload.get("answers"):
                try:
                    plans_mod.save_answers(self.root, payload.get("answers"), payload.get("mode"))
                except PolierError as exc:
                    raise ApiError(400, str(exc))
            info = plans_mod.record_prompt(self.root, self.package_root)
            try:
                session = self.sessions.start(role="generator", prompt=info["text"],
                                              model=payload.get("model") or None)
            except PolierError as exc:
                raise ApiError(400, str(exc))
            draft = runtime_mod.read_json(runtime_mod.runtime_dir(self.root) / plans_mod.PLAN)
            draft.setdefault("prompt", {})["session"] = session["id"]
            runtime_mod.write_json(runtime_mod.runtime_dir(self.root) / plans_mod.PLAN, draft)
            self.bus.publish("session", session)
            return 200, {"session": session, "prompt_path": info["path"]}
        if path == "/api/plan/approve" and method == "POST":
            try:
                result = plans_mod.approve(self.root, self.package_root)
            except PolierError as exc:
                raise ApiError(400, str(exc))
            self.bus.publish("state", {"plan": "approved", "result": result})
            self.invalidate()
            return 200, result
        if path == "/api/plan/tasks" and method == "POST":
            payload = self._json(body)
            if payload.get("template"):
                try:
                    defaults = templates_mod.defaults(self.root, str(payload["template"]))
                except KeyError:
                    raise ApiError(404, "unknown template")
                except PolierError as exc:
                    raise ApiError(400, str(exc))
                payload = {**defaults, **{key: value for key, value in payload.items()
                                          if key != "template" and value is not None}}
            try:
                task = plan_edit.create_task(self.root, payload)
            except PolierError as exc:
                raise ApiError(400, str(exc))
            self.bus.publish("state", {"plan": "task-created", "task": task.get("id")})
            self.invalidate()
            return 200, task
        match = re.fullmatch(r"/api/plan/tasks/([A-Za-z0-9_.-]+)", path)
        if match and method in ("PATCH", "PUT"):
            payload = self._json(body)
            try:
                task = plan_edit.update_task(self.root, match.group(1), payload)
            except KeyError:
                raise ApiError(404, "unknown task")
            except PolierError as exc:
                raise ApiError(400, str(exc))
            self.bus.publish("state", {"plan": "task-updated", "task": task.get("id")})
            self.invalidate()
            return 200, task
        if match and method == "DELETE":
            try:
                result = plan_edit.delete_task(self.root, match.group(1))
            except KeyError:
                raise ApiError(404, "unknown task")
            except PolierError as exc:
                raise ApiError(400, str(exc))
            self.bus.publish("state", {"plan": "task-deleted", "task": result.get("id")})
            self.invalidate()
            return 200, result
        match = re.fullmatch(r"/api/plan/stages/([A-Za-z0-9_.-]+)/(decision|move)", path)
        if match and method == "POST":
            stage_id, verb = match.group(1), match.group(2)
            payload = self._json(body)
            try:
                if verb == "decision":
                    result = plan_edit.set_stage_decision(self.root, stage_id,
                                                          str(payload.get("decision") or ""))
                else:
                    result = plan_edit.move_stage(self.root, stage_id, int(payload.get("delta") or 0))
            except KeyError:
                raise ApiError(404, "unknown stage")
            except PolierError as exc:
                raise ApiError(400, str(exc))
            self.bus.publish("state", {"plan": f"stage-{verb}", "stage": stage_id})
            self.invalidate()
            return 200, result
        # settings, labels, views, worklog, inbox (2.1) -------------------
        if path == "/api/settings" and method == "GET":
            project = settings_mod.load(self.root, strict=False)
            return 200, {
                "project": project,
                "errors": settings_mod.errors(project),
                "features": settings_mod.features(project),
                "feature_defaults": dict(settings_mod.FEATURES),
                "labels": settings_mod.label_list(project),
                "palette": list(settings_mod.PALETTE),
                "groups": list(settings_mod.GROUPS),
                "me": settings_mod.me(project),
                "local": self.config_view(),
            }
        if path == "/api/settings" and method in ("PUT", "POST"):
            payload = self._json(body)
            unknown = set(payload) - {"features", "defaults", "labels"}
            if unknown:
                raise ApiError(400, "unknown settings field(s): " + ", ".join(sorted(unknown)))
            project = settings_mod.load(self.root, strict=False)
            if isinstance(payload.get("features"), dict):
                merged = dict(project.get("features") or {})
                merged.update(payload["features"])
                project["features"] = merged
            if isinstance(payload.get("defaults"), dict):
                merged = dict(project.get("defaults") or {})
                merged.update(payload["defaults"])
                project["defaults"] = merged
            if payload.get("labels") is not None:
                project["labels"] = payload["labels"]
            try:
                project = settings_mod.save(self.root, project)
            except PolierError as exc:
                raise ApiError(400, str(exc))
            self.bus.publish("settings", {"settings": project})
            self.invalidate()
            return 200, {"project": project, "features": settings_mod.features(project),
                         "labels": settings_mod.label_list(project),
                         "me": settings_mod.me(project)}
        if path == "/api/settings/labels" and method == "POST":
            payload = self._json(body)
            try:
                result = settings_mod.add_label(self.root, payload)
            except PolierError as exc:
                raise ApiError(400, str(exc))
            self.bus.publish("settings", {"label": result.get("label")})
            self.invalidate()
            return 200, result
        match = re.fullmatch(r"/api/settings/labels/([a-z][a-z0-9-]{0,40})", path)
        if match and method in ("PUT", "PATCH"):
            payload = self._json(body)
            try:
                result = settings_mod.update_label(self.root, match.group(1), payload)
            except KeyError:
                raise ApiError(404, "unknown label")
            except PolierError as exc:
                raise ApiError(400, str(exc))
            self.bus.publish("settings", {"label": result.get("label")})
            self.invalidate()
            return 200, result
        if match and method == "DELETE":
            payload = self._json(body)
            try:
                result = settings_mod.delete_label(self.root, match.group(1),
                                                   force=bool(payload.get("force")))
            except KeyError:
                raise ApiError(404, "unknown label")
            except PolierError as exc:
                raise ApiError(400, str(exc))
            self.bus.publish("settings", {"deleted_label": match.group(1)})
            self.invalidate()
            return 200, result
        if path == "/api/filters/fields" and method == "GET":
            return 200, {"fields": filters_mod.FIELDS, "operators": filters_mod.OPERATORS,
                         "group_by": list(filters_mod.GROUP_BY),
                         "sortable": list(filters_mod.SORTABLE),
                         "status_order": list(filters_mod.STATUS_ORDER)}
        if path == "/api/views" and method == "GET":
            me = settings_mod.me(settings_mod.load(self.root, strict=False))
            return 200, {"builtin": filters_mod.builtin_views(me),
                         "saved": views_mod.load_all(self.root),
                         "all": views_mod.all_views(self.root, me)}
        match = re.fullmatch(r"/api/views/([a-z][a-z0-9-]{0,40})", path)
        if match and method in ("PUT", "POST"):
            payload = self._json(body)
            payload["id"] = match.group(1)
            payload.setdefault("created_by", self.role)
            try:
                view = views_mod.save(self.root, payload)
            except PolierError as exc:
                raise ApiError(400, str(exc))
            self.bus.publish("views", {"view": view})
            return 200, view
        if match and method == "DELETE":
            try:
                result = views_mod.delete(self.root, match.group(1))
            except KeyError:
                raise ApiError(404, "unknown view")
            except PolierError as exc:
                raise ApiError(400, str(exc))
            self.bus.publish("views", {"deleted": match.group(1)})
            return 200, result
        if path == "/api/worklog" and method == "GET":
            if query.get("task"):
                try:
                    detail = dashboard_mod.task_detail(self.root, query["task"])
                except KeyError:
                    raise ApiError(404, "unknown task")
                return 200, detail["worklog"]
            snapshot = self.snapshot()
            return 200, worklog_mod.project_worklog(self.root, snapshot["tasks"])
        if path == "/api/me" and method == "GET":
            return 200, inbox_mod.your_work(self.root, snapshot=self.snapshot())
        if path == "/api/inbox" and method == "GET":
            summary = inbox_mod.inbox_summary(self.root, snapshot=self.snapshot())
            items = summary["items"]
            if query.get("unread") in ("1", "true", "yes"):
                items = [item for item in items if not item.get("read")]
            return 200, {"items": items, "counts": summary["counts"]}
        if path == "/api/inbox/read" and method == "POST":
            payload = self._json(body)
            ids = payload.get("ids") if isinstance(payload.get("ids"), list) else []
            state = inbox_mod.mark_read(self.root, [str(item) for item in ids],
                                        read=bool(payload.get("read", True)),
                                        all_items=bool(payload.get("all")),
                                        reset=bool(payload.get("reset")))
            self.bus.publish("inbox", {"counts": inbox_mod.inbox_summary(
                self.root, snapshot=self.snapshot())["counts"]})
            return 200, state
        # planning views (2.2): timeline, cycles, modules, coverage, analytics
        if path == "/api/timeline" and method == "GET":
            try:
                return 200, timeline_mod.build(self.root)
            except PolierError as exc:
                raise ApiError(400, str(exc))
        if path == "/api/cycles" and method == "GET":
            return 200, cycles_mod.build(self.root, snapshot=self.snapshot())
        if path == "/api/modules" and method == "GET":
            snapshot = self.snapshot()
            return 200, modules_mod.build(self.root, snapshot=snapshot)
        if path == "/api/coverage" and method == "GET":
            return 200, coverage_mod.build(self.root, snapshot=self.snapshot())
        if path == "/api/analytics" and method == "GET":
            return 200, analytics_mod.build(self.root, snapshot=self.snapshot())
        # pages, intake and task templates (2.3) ---------------------------
        if path == "/api/pages" and method == "GET":
            return 200, pages_mod.index(self.root)
        if path == "/api/pages/search" and method == "GET":
            return 200, {"query": query.get("q") or "",
                         "results": pages_mod.search(self.root, query.get("q") or "",
                                                     int(query.get("limit") or 50))}
        if path == "/api/pages/favorites" and method == "GET":
            return 200, pages_mod.load_favorites(self.root)
        if path == "/api/pages/favorites" and method in ("PUT", "POST"):
            payload = self._json(body)
            paths = payload.get("favorites") if isinstance(payload.get("favorites"), list) else []
            return 200, pages_mod.set_favorites(self.root, paths)
        if path == "/api/page/history" and method == "GET":
            try:
                return 200, {"path": query.get("path"),
                             "history": pages_mod.history(self.root, query.get("path") or "",
                                                          int(query.get("limit") or 20))}
            except KeyError:
                raise ApiError(404, "unknown page")
        if path == "/api/page" and method == "GET":
            try:
                return 200, pages_mod.page(self.root, query.get("path") or "",
                                           query.get("ref") or None)
            except KeyError:
                raise ApiError(404, "unknown page")
            except PolierError as exc:
                raise ApiError(400, str(exc))
        if path == "/api/intake" and method == "GET":
            status = query.get("status")
            if status and status not in intake_mod.STATUSES:
                raise ApiError(400, "unknown intake status")
            return 200, {"entries": intake_mod.load_all(self.root, status or None),
                         **intake_mod.summary(self.root)}
        if path == "/api/intake" and method == "POST":
            payload = self._json(body)
            try:
                entry = intake_mod.create(self.root, payload, by=self.role,
                                          source=str(payload.get("source") or "web"))
            except PolierError as exc:
                raise ApiError(400, str(exc))
            self.bus.publish("intake", {"entry": entry})
            self.invalidate()
            return 200, entry
        match = re.fullmatch(r"/api/intake/(IN-[0-9]{3,})", path)
        if match and method == "GET":
            try:
                return 200, intake_mod.get(self.root, match.group(1))
            except KeyError:
                raise ApiError(404, "unknown intake entry")
        if match and method in ("PUT", "PATCH"):
            payload = self._json(body)
            try:
                entry = intake_mod.update(self.root, match.group(1), payload)
            except KeyError:
                raise ApiError(404, "unknown intake entry")
            except PolierError as exc:
                raise ApiError(400, str(exc))
            self.bus.publish("intake", {"entry": entry})
            return 200, entry
        match = re.fullmatch(r"/api/intake/(IN-[0-9]{3,})/accept", path)
        if match and method == "POST":
            payload = self._json(body)
            task_payload = dict(payload.get("task") or {}) if isinstance(payload.get("task"), dict) else {}
            for key in ("stage", "owner", "package", "complexity", "estimate_hours", "labels",
                        "scope_write", "scope_read", "acceptance", "gates", "depends_on",
                        "exclusive", "id"):
                if key in payload and key not in task_payload:
                    task_payload[key] = payload[key]
            template = payload.get("template") or task_payload.pop("template", None)
            try:
                result = intake_mod.accept(
                    self.root, match.group(1), by=str(payload.get("by") or self.role),
                    note=str(payload.get("note") or ""),
                    task_payload=task_payload,
                    template=template)
            except KeyError:
                raise ApiError(404, "unknown intake entry")
            except PolierError as exc:
                raise ApiError(400, str(exc))
            self.bus.publish("intake", {"entry": result["intake"]})
            self.bus.publish("state", {"task": result["task"].get("id"), "status": "pending"})
            self.invalidate()
            return 200, result
        match = re.fullmatch(r"/api/intake/(IN-[0-9]{3,})/reject", path)
        if match and method == "POST":
            payload = self._json(body)
            try:
                entry = intake_mod.reject(self.root, match.group(1),
                                          by=str(payload.get("by") or self.role),
                                          note=str(payload.get("note") or ""))
            except KeyError:
                raise ApiError(404, "unknown intake entry")
            except PolierError as exc:
                raise ApiError(400, str(exc))
            self.bus.publish("intake", {"entry": entry})
            return 200, entry
        if path == "/api/task-templates" and method == "GET":
            return 200, {"templates": templates_mod.load_all(self.root)}
        if path == "/api/task-templates" and method == "POST":
            payload = self._json(body)
            try:
                if payload.get("from_task"):
                    template = templates_mod.from_task(
                        self.root, str(payload["from_task"]), str(payload.get("id") or ""),
                        name=payload.get("name") or None)
                else:
                    template = templates_mod.save(self.root, payload)
            except KeyError:
                raise ApiError(404, "unknown task")
            except PolierError as exc:
                raise ApiError(400, str(exc))
            self.bus.publish("templates", {"template": template})
            return 200, template
        match = re.fullmatch(r"/api/task-templates/([a-z][a-z0-9-]{0,40})", path)
        if match and method == "DELETE":
            try:
                result = templates_mod.delete(self.root, match.group(1))
            except KeyError:
                raise ApiError(404, "unknown template")
            except PolierError as exc:
                raise ApiError(400, str(exc))
            self.bus.publish("templates", {"deleted": match.group(1)})
            return 200, result
        # files / audit ----------------------------------------------------
        if path == "/api/files" and method == "GET":
            try:
                return 200, dashboard_mod.repo_files(self.root, query.get("prefix", ""))
            except PolierError as exc:
                raise ApiError(400, str(exc))
        if path == "/api/file" and method == "GET":
            try:
                return 200, dashboard_mod.file_preview(self.root, query.get("path", ""))
            except PolierError as exc:
                raise ApiError(404, str(exc))
        if path == "/api/audit" and method == "GET":
            return 200, audit_mod.audit(self.root)
        raise ApiError(404, f"no route for {method} {path}")

    def _json(self, body: Optional[bytes]) -> Dict[str, Any]:
        if body is None or not body.strip():
            return {}
        if len(body) > MAX_BODY:
            raise ApiError(413, "request body too large")
        try:
            value = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ApiError(400, f"invalid JSON: {exc}")
        if not isinstance(value, dict):
            raise ApiError(400, "JSON body must be an object")
        return value


class _Sse(Exception):
    pass


class _Bus:
    """Thin wrapper so the bus import stays optional in tests."""

    def __init__(self) -> None:
        from core.bus import EventBus

        self._bus = EventBus()

    def publish(self, topic: str, data: Any = None) -> None:
        self._bus.publish(topic, data if isinstance(data, dict) else {"value": data})

    def subscribe(self):
        return self._bus.subscribe()

    def stats(self) -> Dict[str, Any]:
        return self._bus.stats()


class _Watcher(threading.Thread):
    """Polls the project stores and publishes one `state` event per change."""

    def __init__(self, app: DashboardApp) -> None:
        super().__init__(daemon=True, name="polier-dashboard-watch")
        self.app = app
        self._stop = threading.Event()
        self._signature = ""
        self._interval = 1.0

    def run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                signature = self.app.signature()
            except Exception:  # noqa: BLE001
                continue
            if signature != self._signature:
                self._signature = signature
                self.app.invalidate()
                self.app.bus.publish("state", {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

    def stop(self) -> None:
        self._stop.set()


def _stamp(path: Path) -> str:
    try:
        stat = path.stat()
        return f"{path.name}:{int(stat.st_mtime * 1000)}:{stat.st_size}"
    except OSError:
        return f"{path.name}:-"


def _dir_stamp(path: Path) -> str:
    try:
        names = sorted(entry.name for entry in path.iterdir())
        return f"{path.name}:{len(names)}:{int(path.stat().st_mtime * 1000)}"
    except OSError:
        return f"{path.name}:-"


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"PolierDashboard/{VERSION}"
    app: DashboardApp

    def log_message(self, fmt: str, *args: Any) -> None:  # keep the terminal quiet
        if not self.app.quiet:
            return

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") == "/api/events" and method == "GET":
            self._events(parsed)
            return
        length = int(self.headers.get("content-length") or 0) or None
        body = self.rfile.read(length) if length else None
        status, content_type, payload = self.app.handle(method, self.path, body, self.headers)
        extra = {}
        if method == "GET" and parsed.path.rstrip("/") in ("", "/index.html") and self.app.token:
            token = {key: values[-1] for key, values in parse_qs(parsed.query).items()}.get("token")
            if token and secrets.compare_digest(token, self.app.token):
                extra["Set-Cookie"] = (f"polier_token={token}; HttpOnly; SameSite=Strict; "
                                       f"Path=/; Max-Age=86400")
        if isinstance(payload, bytes):
            data = payload
        else:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, content_type, data, extra)

    def _send(self, status: int, content_type: str, data: bytes,
              extra: Optional[Dict[str, str]] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if content_type.startswith("text/html"):
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                             "img-src 'self' data:; connect-src 'self'; font-src 'self'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _events(self, parsed) -> None:
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        headers = self.headers
        try:
            self.app._check_auth("GET", "/api/events", query, headers)
        except ApiError as exc:
            data = json.dumps({"error": exc.message}).encode("utf-8")
            self._send(exc.status, "application/json", data)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        subscription = self.app.bus.subscribe()
        try:
            payload = json.dumps({"version": VERSION, "role": self.app.role}, ensure_ascii=False)
            self.wfile.write(f"event: ready\ndata: {payload}\n\n".encode("utf-8"))
            self.wfile.flush()
            while True:
                event = subscription.get(timeout=15.0)
                if event is None:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                topic = str(event.get("topic") or "message")
                data = json.dumps(event, ensure_ascii=False)
                self.wfile.write(f"event: {topic}\ndata: {data}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            subscription.close()

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")

    def do_PATCH(self) -> None:  # noqa: N802
        self._dispatch("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")


class DashboardServer:
    """A threaded HTTP server bound to one DashboardApp."""

    def __init__(self, app: DashboardApp, *, port: Optional[int] = None) -> None:
        self.app = app
        handler = type("BoundHandler", (_Handler,), {"app": app})
        self.httpd = ThreadingHTTPServer((app.host, int(port if port is not None else app.port)), handler)
        self.httpd.daemon_threads = True
        self.app.port = self.httpd.server_address[1]
        self.thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        host = self.app.host
        if host in ("0.0.0.0", "::"):
            host = "127.0.0.1"
        suffix = f"?token={self.app.token}" if self.app.token else ""
        return f"http://{host}:{self.app.port}{suffix}"

    def start(self, *, open_browser: bool = False) -> "DashboardServer":
        self.app.watcher.start()
        self.app.watcher._signature = self.app.signature()
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True, name="polier-dashboard-http")
        self.thread.start()
        if open_browser or self.app.open_browser:
            threading.Timer(0.4, lambda: webbrowser.open(self.url)).start()
        return self

    def serve_forever(self) -> None:
        self.start()
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            self.shutdown()

    def shutdown(self) -> None:
        self.app.watcher.stop()
        self.httpd.shutdown()
        self.httpd.server_close()

    # context manager for tests
    def __enter__(self) -> "DashboardServer":
        return self.start()

    def __exit__(self, *exc: Any) -> None:
        self.shutdown()


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Start the Polier dashboard for a project (zero dependencies).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example: python3 tools/serve.py . --port 8765 --open")
    parser.add_argument("project", nargs="?", default=".", help="project folder (default: .)")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="port (default: 8765; 0 picks a free one)")
    parser.add_argument("--token", default=os.environ.get("POLIER_DASHBOARD_TOKEN"),
                        help="require this token (default: $POLIER_DASHBOARD_TOKEN, empty = none)")
    parser.add_argument("--role", default="lead", choices=("lead", "viewer"),
                        help="lead writes, viewer reads (default: lead)")
    parser.add_argument("--read-only", action="store_true", help="refuse every write")
    parser.add_argument("--open", action="store_true", help="open the browser")
    parser.add_argument("--quiet", action="store_true", help="no request logging")
    args = parser.parse_args(argv)

    root = Path(args.project).resolve()
    if not root.is_dir():
        print(f"serve.py: not a folder: {root}")
        return 2
    app = DashboardApp(root, host=args.host, port=args.port, token=args.token,
                       role=args.role, read_only=args.read_only,
                       open_browser=args.open, quiet=args.quiet)
    server = DashboardServer(app, port=args.port)
    print(f"Polier dashboard {VERSION} — {server.url}")
    print(f"project: {root}")
    print(f"role: {app.role}{' (read-only)' if app.read_only else ''}")
    if not (root / "board.json").is_file():
        print("note: no board.json yet — open the dashboard and start the interview wizard")
    if app.host not in ("127.0.0.1", "localhost", "::1") and not app.token:
        print("warning: binding to a non-loopback address without --token")
    server.serve_forever()
    return 0
