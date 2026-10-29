"""MCP connectors (2.5): external MCP servers that agent sessions may use.

A connector is one MCP server — a local command (stdio) or a remote endpoint
(streamable HTTP) — that headless sessions and the assistant get as tools. They
are configured per machine in the dashboard runtime config
(``<git-common-dir>/polier/dashboard/config.json`` → ``mcp_servers``), never
committed, because they carry local paths and secrets. Secret values (env and
header values) are masked in every response.

Polier's own MCP server (``tools/mcp.py``) is offered as the built-in
connector ``polier``; it is read-only for sessions unless switched otherwise.

For a Claude Code session the enabled connectors become a ``--mcp-config``
file and ``mcp__<name>`` entries in the allowed tools.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .errors import PolierError

NAME = re.compile(r"^[a-z][a-z0-9_-]{0,40}$")
TYPES = ("stdio", "http")
ROLES = ("worker", "reviewer", "lead", "assistant", "generator")
MASK = "••••••"
FIELDS = frozenset({"type", "command", "args", "env", "url", "headers", "enabled", "roles", "description"})
BUILTIN = "polier"
PROTOCOL = "2025-03-26"


def _strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _mapping(value: Any) -> bool:
    return isinstance(value, dict) and all(isinstance(key, str) and isinstance(item, str)
                                           for key, item in value.items())


def errors(name: str, entry: Dict[str, Any]) -> List[str]:
    found: List[str] = []
    if not NAME.match(name or ""):
        found.append("name must be lowercase (a-z, 0-9, '-', '_')")
    if name == BUILTIN:
        found.append(f"'{BUILTIN}' is the built-in connector")
    if not isinstance(entry, dict):
        return found + ["connector must be an object"]
    for field in sorted(set(entry) - FIELDS):
        found.append(f"unknown field {field!r}")
    kind = entry.get("type", "stdio")
    if kind not in TYPES:
        found.append("type must be stdio or http")
    if kind == "stdio":
        if not isinstance(entry.get("command"), str) or not entry["command"].strip():
            found.append("a stdio connector needs a command")
        if "args" in entry and not _strings(entry["args"]):
            found.append("args must be a list of strings")
        if "env" in entry and not _mapping(entry["env"]):
            found.append("env must map names to strings")
    if kind == "http":
        url = entry.get("url")
        if not isinstance(url, str) or not re.match(r"^https?://", url):
            found.append("an http connector needs an http(s) url")
        if "headers" in entry and not _mapping(entry["headers"]):
            found.append("headers must map names to strings")
    if "roles" in entry and (not _strings(entry["roles"]) or any(role not in ROLES for role in entry["roles"])):
        found.append(f"roles must be a subset of {', '.join(ROLES)}")
    if "enabled" in entry and not isinstance(entry["enabled"], bool):
        found.append("enabled must be true or false")
    if "description" in entry and (not isinstance(entry["description"], str) or len(entry["description"]) > 200):
        found.append("description must be at most 200 characters")
    return [f"connector {name or '?'}: {problem}" for problem in found]


def _masked(values: Dict[str, str]) -> Dict[str, str]:
    return {key: (MASK if value else "") for key, value in (values or {}).items()}


def builtin_settings(config: Dict[str, Any]) -> Dict[str, Any]:
    value = config.get("polier_mcp") if isinstance(config.get("polier_mcp"), dict) else {}
    return {"enabled": bool(value.get("enabled", True)), "read_only": bool(value.get("read_only", True)),
            "roles": [role for role in value.get("roles", ["worker", "reviewer", "lead", "assistant"]) if role in ROLES]}


def view(config: Dict[str, Any], package_root, root) -> Dict[str, Any]:
    """Connectors for the UI and the API, secrets masked."""
    servers = config.get("mcp_servers") if isinstance(config.get("mcp_servers"), dict) else {}
    entries: List[Dict[str, Any]] = []
    builtin = builtin_settings(config)
    entries.append({
        "name": BUILTIN, "builtin": True, "type": "stdio", "enabled": builtin["enabled"],
        "read_only": builtin["read_only"], "roles": builtin["roles"],
        "description": "This project's board, tasks, dispatch and evidence as tools.",
        "command": sys.executable, "args": polier_args(package_root, root, builtin["read_only"]),
        "env": {}, "headers": {}, "url": None,
    })
    for name in sorted(servers):
        entry = servers[name] if isinstance(servers[name], dict) else {}
        entries.append({
            "name": name, "builtin": False, "type": entry.get("type", "stdio"),
            "enabled": bool(entry.get("enabled", True)),
            "roles": entry.get("roles") or list(ROLES),
            "description": entry.get("description") or "",
            "command": entry.get("command"), "args": entry.get("args") or [],
            "env": _masked(entry.get("env") or {}), "url": entry.get("url"),
            "headers": _masked(entry.get("headers") or {}),
            "errors": errors(name, entry),
        })
    return {"connectors": entries, "roles": list(ROLES), "types": list(TYPES)}


def upsert(config: Dict[str, Any], name: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    """Add or replace one connector; masked secret values keep their stored value."""
    if name == BUILTIN:
        unknown = set(entry or {}) - {"enabled", "read_only", "roles", "name", "builtin", "type"}
        if unknown:
            raise PolierError(f"the built-in connector only takes enabled, read_only and roles (got {', '.join(sorted(unknown))})")
        builtin = builtin_settings(config)
        for key in ("enabled", "read_only"):
            if key in entry:
                if not isinstance(entry[key], bool):
                    raise PolierError(f"{key} must be true or false")
                builtin[key] = entry[key]
        if "roles" in entry:
            if not _strings(entry["roles"]) or any(role not in ROLES for role in entry["roles"]):
                raise PolierError(f"roles must be a subset of {', '.join(ROLES)}")
            builtin["roles"] = entry["roles"]
        config["polier_mcp"] = builtin
        return config
    servers = dict(config.get("mcp_servers") or {})
    previous = servers.get(name) if isinstance(servers.get(name), dict) else {}
    clean = {key: value for key, value in (entry or {}).items() if key not in ("name", "builtin", "errors", "read_only")}
    for field in ("env", "headers"):
        if isinstance(clean.get(field), dict):
            old = previous.get(field) or {}
            clean[field] = {key: (old.get(key, "") if value == MASK else value)
                            for key, value in clean[field].items()}
    kind = clean.get("type", "stdio")
    for field in (("url", "headers") if kind == "stdio" else ("command", "args", "env")):
        clean.pop(field, None)
    problems = errors(name, clean)
    if problems:
        raise PolierError("; ".join(problems))
    servers[name] = clean
    config["mcp_servers"] = servers
    return config


def remove(config: Dict[str, Any], name: str) -> Dict[str, Any]:
    servers = dict(config.get("mcp_servers") or {})
    if name not in servers:
        raise KeyError(name)
    servers.pop(name)
    config["mcp_servers"] = servers
    return config


def polier_args(package_root, root, read_only: bool) -> List[str]:
    args = [str(Path(package_root) / "tools" / "mcp.py"), "--root", str(root)]
    return args + ["--read-only"] if read_only else args


def _claude_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    if entry.get("type") == "http":
        value = {"type": "http", "url": entry["url"]}
        if entry.get("headers"):
            value["headers"] = dict(entry["headers"])
        return value
    value = {"command": entry["command"], "args": list(entry.get("args") or [])}
    if entry.get("env"):
        value["env"] = dict(entry["env"])
    return value


def for_session(config: Dict[str, Any], role: str, package_root, root,
                only: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
    """The connectors a session of ``role`` gets (optionally limited to ``only``)."""
    chosen: Dict[str, Dict[str, Any]] = {}
    builtin = builtin_settings(config)
    if builtin["enabled"] and role in builtin["roles"] and (only is None or BUILTIN in only or not only):
        chosen[BUILTIN] = {"command": sys.executable,
                           "args": polier_args(package_root, root, builtin["read_only"] or role != "lead")}
    servers = config.get("mcp_servers") if isinstance(config.get("mcp_servers"), dict) else {}
    for name, entry in sorted(servers.items()):
        if not isinstance(entry, dict) or errors(name, entry) or not entry.get("enabled", True):
            continue
        if role not in (entry.get("roles") or ROLES):
            continue
        if only and name not in only:
            continue
        chosen[name] = _claude_entry(entry)
    return chosen


def claude_config(servers: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return {"mcpServers": servers}


# -- connection test ---------------------------------------------------------

def _rpc(method: str, request_id: Optional[int], params: Optional[dict] = None) -> Dict[str, Any]:
    message: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        message["id"] = request_id
    if params is not None:
        message["params"] = params
    return message


INIT_PARAMS = {"protocolVersion": PROTOCOL, "capabilities": {},
               "clientInfo": {"name": "polier-dashboard", "version": "2.5"}}


def _test_stdio(entry: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    command = str(entry.get("command") or "")
    executable = shutil.which(command) or (command if Path(command).is_file() else None)
    if not executable:
        return {"ok": False, "error": f"command not found: {command}"}
    env = {**os.environ, **(entry.get("env") or {})}
    try:
        process = subprocess.Popen([executable, *(entry.get("args") or [])], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    replies: Dict[int, Dict[str, Any]] = {}
    done = threading.Event()

    def reader() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if isinstance(message, dict) and isinstance(message.get("id"), int):
                replies[message["id"]] = message
                if 2 in replies:
                    break
        done.set()

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        assert process.stdin is not None
        process.stdin.write(json.dumps(_rpc("initialize", 1, INIT_PARAMS)) + "\n")
        process.stdin.write(json.dumps(_rpc("notifications/initialized", None)) + "\n")
        process.stdin.write(json.dumps(_rpc("tools/list", 2, {})) + "\n")
        process.stdin.flush()
        done.wait(timeout)
    except (BrokenPipeError, OSError):
        pass
    finally:
        try:
            process.kill()
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
    stderr = ""
    if not replies and process.stderr:
        try:
            stderr = process.stderr.read()
        except (OSError, ValueError):
            stderr = ""
    for stream in (process.stdin, process.stdout, process.stderr):
        try:
            if stream:
                stream.close()
        except (OSError, ValueError):
            pass
    return _result(replies.get(1), replies.get(2), stderr)


def _post(url: str, headers: Dict[str, str], message: Dict[str, Any],
          timeout: float) -> Tuple[Optional[Dict[str, Any]], Dict[str, str]]:
    data = json.dumps(message).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream", **headers})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - the owner's own URL
        body = response.read().decode("utf-8", errors="replace")
        reply_headers = {key.lower(): value for key, value in response.headers.items()}
    if "text/event-stream" in reply_headers.get("content-type", ""):
        for line in body.splitlines():
            if line.startswith("data:"):
                try:
                    value = json.loads(line[5:].strip())
                except ValueError:
                    continue
                if isinstance(value, dict) and "id" in value:
                    return value, reply_headers
        return None, reply_headers
    return (json.loads(body) if body.strip() else None), reply_headers


def _test_http(entry: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    headers = dict(entry.get("headers") or {})
    try:
        init, reply_headers = _post(entry["url"], headers, _rpc("initialize", 1, INIT_PARAMS), timeout)
        session = reply_headers.get("mcp-session-id")
        if session:
            headers["Mcp-Session-Id"] = session
        try:
            _post(entry["url"], headers, _rpc("notifications/initialized", None), timeout)
        except (urllib.error.URLError, ValueError, OSError):
            pass
        tools, _ = _post(entry["url"], headers, _rpc("tools/list", 2, {}), timeout)
    except urllib.error.HTTPError as exc:
        hint = " — check the token or headers" if exc.code in (401, 403) else ""
        return {"ok": False, "error": f"HTTP {exc.code}{hint}"}
    except (urllib.error.URLError, ValueError, OSError) as exc:
        return {"ok": False, "error": str(getattr(exc, "reason", exc))}
    return _result(init, tools, "")


def _result(init: Optional[Dict[str, Any]], tools: Optional[Dict[str, Any]], stderr: str) -> Dict[str, Any]:
    if not init:
        return {"ok": False, "error": ("no answer to initialize" + (f": {stderr.strip()[:300]}" if stderr.strip() else ""))}
    if "error" in init:
        return {"ok": False, "error": str(init["error"].get("message") if isinstance(init["error"], dict) else init["error"])}
    info = (init.get("result") or {}).get("serverInfo") or {}
    names = [str(tool.get("name")) for tool in ((tools or {}).get("result") or {}).get("tools") or []
             if isinstance(tool, dict)]
    return {"ok": True, "server": info.get("name") or "", "version": info.get("version") or "",
            "protocol": (init.get("result") or {}).get("protocolVersion"), "tools": names}


def test(config: Dict[str, Any], name: str, package_root, root, timeout: float = 20.0) -> Dict[str, Any]:
    """Connect once (initialize + tools/list) and report the server and its tools."""
    if name == BUILTIN:
        entry = {"type": "stdio", "command": sys.executable,
                 "args": polier_args(package_root, root, builtin_settings(config)["read_only"])}
    else:
        servers = config.get("mcp_servers") if isinstance(config.get("mcp_servers"), dict) else {}
        if name not in servers:
            raise KeyError(name)
        entry = servers[name]
        problems = errors(name, entry)
        if problems:
            return {"ok": False, "error": "; ".join(problems)}
    if entry.get("type") == "http":
        return _test_http(entry, timeout)
    return _test_stdio(entry, timeout)
