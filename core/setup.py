"""Guided first-run setup for the dashboard.

The setup state is machine-local: it lives in the dashboard runtime config
(``<git-common-dir>/polier/dashboard/config.json``), never in the project files,
because whether this machine has a provider installed and logged in says
nothing about the team's project. The dashboard asks once on first run; the
operator may skip the wizard and reopen it later from the settings page.

The provider probes are deliberately read-only and best-effort: a missing
binary, a timeout or an unreadable answer only means "unknown", never an error.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .errors import PolierError

STATE_VERSION = 1
STATUSES = ("pending", "done", "skipped")
ACTIONS = {"complete": "done", "skip": "skipped", "reset": "pending"}
AUTH_TIMEOUT = 8

# The providers the wizard offers, in display order. ``command`` is the preset
# looked up per provider; a custom command comes from the session settings.
PROVIDERS: List[Dict[str, Any]] = [
    {"id": "claude", "label": "Claude Code", "command": ["claude"], "login_command": "claude auth login",
     "models": ["opus", "sonnet", "haiku"],
     "hint": "Polier runs the Claude Code CLI headlessly and reads its JSON events."},
    {"id": "custom", "label": "Custom command", "command": None, "login_command": None, "models": [],
     "hint": "A command that prints Claude Code-style JSON events; Polier appends the prompt as its last argument."},
]


def read(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The normalized setup record: version, status and when it last changed.

    Missing or malformed state reads as ``pending`` so the wizard is offered
    again; this never raises.
    """
    value = config.get("setup") if isinstance(config, dict) else None
    value = value if isinstance(value, dict) else {}
    status = value.get("status")
    if status not in STATUSES:
        status = "pending"
    updated_at = value.get("updated_at")
    return {
        "version": STATE_VERSION,
        "status": status,
        "updated_at": updated_at if isinstance(updated_at, str) and updated_at else None,
    }


def initial(config_existed: bool) -> Dict[str, Any]:
    """The record for a runtime config that has no setup state yet.

    A machine that never ran the dashboard starts ``pending`` so the wizard
    opens once. An existing dashboard runtime (a config file was already
    there) counts as ``skipped``: upgrading must not open the wizard by itself,
    it stays reachable from the sidebar and the settings page.
    """
    return {
        "version": STATE_VERSION,
        "status": "skipped" if config_existed else "pending",
        "updated_at": None,
    }


def mark(config: Dict[str, Any], action: str) -> Dict[str, Any]:
    """Apply a setup action to config and return the stored record."""
    status = ACTIONS.get(action)
    if status is None:
        raise PolierError(f"unknown setup action {action!r}")
    record: Dict[str, Any] = {
        "version": STATE_VERSION,
        "status": status,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    config["setup"] = record
    return record


def _preset(provider_id: str) -> Optional[Dict[str, Any]]:
    return next((provider for provider in PROVIDERS if provider["id"] == provider_id), None)


def _session(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    session = config.get("session") if isinstance(config, dict) else None
    return session if isinstance(session, dict) else {}


def _auth_status(run: Optional[Callable[..., Any]]) -> Tuple[Optional[bool], Optional[str]]:
    """Run ``claude auth status`` and read only its login flags.

    The CLI exits non-zero when the user is signed out but still prints the
    JSON answer, so a valid answer counts whatever the exit code; only an
    unreadable answer, a timeout or a missing binary means "unknown".
    """
    argv = ["claude", "auth", "status"]
    try:
        if run is not None:
            code, stdout, stderr = run(argv, AUTH_TIMEOUT)
        else:
            completed = subprocess.run(argv, capture_output=True, text=True, timeout=AUTH_TIMEOUT)
            code, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
    except Exception:  # noqa: BLE001 - a missing binary or a timeout means "unknown"
        return None, None
    try:
        data = json.loads(stdout or "")
    except (TypeError, ValueError):
        return None, None
    if not isinstance(data, dict) or "loggedIn" not in data:
        return None, None
    return bool(data["loggedIn"]), data.get("authMethod") or None


def provider_status(config: Optional[Dict[str, Any]], *, which: Optional[Callable[[str], Optional[str]]] = None,
                    run: Optional[Callable[..., Any]] = None) -> Dict[str, Any]:
    """What this machine can do with the configured session provider.

    ``which`` and ``run`` exist for tests; the defaults are ``shutil.which`` and
    ``subprocess.run``. The probe never raises and never returns the account
    email or a token.
    """
    session = _session(config)
    provider_id = str(session.get("provider") or "claude")
    command = session.get("command")
    if not (isinstance(command, list) and command and all(isinstance(part, str) for part in command)):
        command = ["claude"]
    model = session.get("model") or None
    find = which or shutil.which
    try:
        path = find(command[0])
    except Exception:  # noqa: BLE001 - a broken PATH helper means "not installed"
        path = None
    installed = bool(path)
    signed_in: Optional[bool] = None
    auth_method: Optional[str] = None
    if provider_id == "claude" and installed:
        signed_in, auth_method = _auth_status(run)
    preset = _preset(provider_id)
    return {
        "id": provider_id,
        "command": command,
        "model": model,
        "installed": installed,
        "path": path or None,
        "signed_in": signed_in,
        "auth_method": auth_method,
        "login_command": preset["login_command"] if preset else None,
        "models": list(preset["models"]) if preset else [],
    }


def payload(*, board_present: bool, config: Dict[str, Any],
            which: Optional[Callable[[str], Optional[str]]] = None,
            run: Optional[Callable[..., Any]] = None) -> Dict[str, Any]:
    """Everything the setup view needs in one response."""
    return {
        "state": read(config),
        "provider": provider_status(config, which=which, run=run),
        "providers": PROVIDERS,
        "board_present": bool(board_present),
    }
