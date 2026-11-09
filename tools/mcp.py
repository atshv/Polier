#!/usr/bin/env python3
"""Polier as an MCP server: connect Claude Code, Claude Desktop, Cursor or any MCP host.

Usage:
    python3 tools/mcp.py [--root .] [--read-only]

Add it to Claude Code with:

    claude mcp add polier -- python3 /path/to/polier/tools/mcp.py --root .

Tools (JSON-RPC ``tools/call``):
    polier_factory       the factory line: stations, progress, findings
    polier_factory_next  open items of the current station
    polier_factory_item  one checklist item with its state
    polier_factory_set   mark an item done / na / deferred / open (write)
    polier_factory_link  link board tasks to an item (write)
    polier_tasks         every task with status, stage and gates
    polier_task          one task: board entry, brief, review, run state
    polier_dispatch      next wave, running, blocked, conflicts
    polier_show          board status against the run record
    polier_approvals     approval records (pending by default)
    polier_claims        live claims
    polier_state_set     lead-only status transition (write)
    polier_gate          run one gate and return its record summary (write)
    polier_claim         take the claim for a task (write)
    polier_release       release the claim of a task (write)

The server speaks newline-delimited JSON-RPC 2.0 on stdio (MCP stdio
transport), runs on the Python standard library only, and writes nothing but
what the called tools do. ``--read-only`` refuses every write tool.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import approvals as approvals_mod  # noqa: E402
from core import board as board_mod  # noqa: E402
from core import claims as claims_mod  # noqa: E402
from core import dispatch as dispatch_mod  # noqa: E402
from core import factory as factory_mod  # noqa: E402
from core import gate as gate_mod  # noqa: E402
from core import runs as runs_mod  # noqa: E402
from core import state as state_mod  # noqa: E402
from core.errors import PolierError  # noqa: E402
from core.gates import suggest_gate_commands  # noqa: E402

PROTOCOL = "2024-11-05"


def _version() -> str:
    try:
        return (Path(__file__).resolve().parent.parent / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


SERVER = {"name": "polier", "version": _version()}
WRITE_TOOLS = {"polier_factory_set", "polier_factory_link", "polier_state_set", "polier_gate",
               "polier_claim", "polier_release"}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _schema(properties: Dict[str, Any] = None, required: List[str] = None) -> Dict[str, Any]:
    value: Dict[str, Any] = {"type": "object", "properties": properties or {}}
    if required:
        value["required"] = required
    return value


TASK = {"task": {"type": "string", "description": "Task ID, e.g. M03"}}
ITEM = {"item": {"type": "string", "description": "Factory item ID, e.g. BLD-30"}}


class Server:
    def __init__(self, root: Path, read_only: bool = False) -> None:
        self.root = root
        self.read_only = read_only

    # -- tools -------------------------------------------------------------
    def tools(self) -> List[Dict[str, Any]]:
        return [
            {"name": "polier_factory", "description": "The factory line: platforms, traits, the nine stations with progress, the current station, errors and warnings.",
             "inputSchema": _schema()},
            {"name": "polier_factory_next", "description": "Open checklist items of the current station with detail and the expected evidence.",
             "inputSchema": _schema({"limit": {"type": "integer"}})},
            {"name": "polier_factory_item", "description": "One checklist item: catalog text, whether it applies, its state and problems.",
             "inputSchema": _schema(ITEM, ["item"])},
            {"name": "polier_factory_set", "description": "Mark an item done (with evidence paths), na or deferred (with a reason) or open. Refused when the state would not hold.",
             "inputSchema": _schema({**ITEM,
                                     "status": {"type": "string", "enum": list(factory_mod.ITEM_STATUSES)},
                                     "evidence": {"type": "array", "items": {"type": "string"}},
                                     "reason": {"type": "string"}}, ["item", "status"])},
            {"name": "polier_factory_link", "description": "Link board tasks that deliver a build or verify item.",
             "inputSchema": _schema({**ITEM, "tasks": {"type": "array", "items": {"type": "string"}}}, ["item", "tasks"])},
            {"name": "polier_tasks", "description": "Every task with status, stage, owner, gates and dependencies.",
             "inputSchema": _schema()},
            {"name": "polier_task", "description": "One task: board entry, brief text, review text and run state.",
             "inputSchema": _schema(TASK, ["task"])},
            {"name": "polier_dispatch", "description": "Next wave, running tasks, blocked tasks and scope conflicts.",
             "inputSchema": _schema()},
            {"name": "polier_show", "description": "Board status against the run record, gates, review and approvals.",
             "inputSchema": _schema(TASK, ["task"])},
            {"name": "polier_approvals", "description": "Approval records; pending by default.",
             "inputSchema": _schema({"status": {"type": "string"}})},
            {"name": "polier_claims", "description": "Live claims of this repository.",
             "inputSchema": _schema()},
            {"name": "polier_state_set", "description": "Lead-only status transition through the state machine.",
             "inputSchema": _schema({**TASK, "status": {"type": "string"}, "note": {"type": "string"}}, ["task", "status"])},
            {"name": "polier_gate", "description": "Run one gate, write its evidence record and return the summary.",
             "inputSchema": _schema({**TASK, "name": {"type": "string"}, "command": {"type": "string"},
                                     "timeout": {"type": "integer"}}, ["task", "name"])},
            {"name": "polier_claim", "description": "Take the claim for a task.",
             "inputSchema": _schema({**TASK, "session": {"type": "string"}}, ["task"])},
            {"name": "polier_release", "description": "Release the claim of a task.",
             "inputSchema": _schema(TASK, ["task"])},
        ]

    def call(self, name: str, arguments: Dict[str, Any]) -> Any:
        arguments = arguments if isinstance(arguments, dict) else {}
        if name in WRITE_TOOLS and self.read_only:
            raise PolierError("this MCP server runs read-only")
        task = _text(arguments.get("task")).upper()
        item = _text(arguments.get("item")).upper()

        if name == "polier_factory":
            value = factory_mod.summary(self.root)
            if value is None:
                raise PolierError("no factory.json; start the line with tools/factory.py init --platforms <list>")
            return value
        if name == "polier_factory_next":
            limit = arguments.get("limit")
            return factory_mod.next_items(self.root, limit=int(limit) if isinstance(limit, int) else 0)
        if name == "polier_factory_item":
            entry_item = factory_mod.catalog_item(item)
            data = factory_mod.load(self.root) or {}
            entry = (data.get("items") or {}).get(entry_item["id"])
            return {**entry_item, "applies": entry is not None, "state": entry,
                    "problems": factory_mod.item_problems(self.root, entry_item["id"], entry) if entry else []}
        if name == "polier_factory_set":
            status = _text(arguments.get("status"))
            evidence = [str(v) for v in arguments.get("evidence") or [] if isinstance(v, str)]
            return factory_mod.set_item(self.root, item, status, evidence=evidence,
                                        reason=_text(arguments.get("reason")) or None, by="mcp")
        if name == "polier_factory_link":
            tasks = [str(v) for v in arguments.get("tasks") or [] if isinstance(v, str)]
            return factory_mod.link(self.root, item, tasks, by="mcp")

        if name == "polier_tasks":
            board = board_mod.load_board(self.root, strict=False) or {}
            keys = ("id", "title", "status", "stage", "owner", "complexity", "gates", "depends_on", "package")
            return [{key: entry.get(key) for key in keys if key in entry}
                    for entry in board.get("tasks") or [] if isinstance(entry, dict)]
        if name == "polier_task":
            if not task:
                raise PolierError("task is required")
            board = board_mod.load_board(self.root, strict=False) or {}
            entry = next((t for t in board.get("tasks") or [] if isinstance(t, dict) and t.get("id") == task), None)
            if entry is None:
                raise PolierError(f"unknown task {task}")
            value: Dict[str, Any] = {"task": entry}
            for key, rel in (("brief", f"tasks/{task}.md"), ("review", f"reviews/{task}.md")):
                path = self.root / rel
                if path.is_file():
                    value[key] = path.read_text(encoding="utf-8")
            try:
                value["state"] = state_mod.status_of(self.root, task)
            except Exception:  # noqa: BLE001 - a project without runs/ still shows the task
                pass
            return value
        if name == "polier_dispatch":
            return dispatch_mod.plan(self.root)
        if name == "polier_show":
            if not task:
                raise PolierError("task is required")
            return state_mod.status_of(self.root, task)
        if name == "polier_approvals":
            status = _text(arguments.get("status")) or "pending"
            return [record for record in approvals_mod.load_all(self.root) if record.get("status") == status]
        if name == "polier_claims":
            return claims_mod.live_claims(self.root)
        if name == "polier_state_set":
            status = _text(arguments.get("status"))
            if not task or not status:
                raise PolierError("task and status are required")
            return state_mod.set_status(self.root, task, status, actor="lead", note=arguments.get("note"))
        if name == "polier_gate":
            gate_name = _text(arguments.get("name"))
            if not task or not gate_name:
                raise PolierError("task and name are required")
            command = _text(arguments.get("command")) or suggest_gate_commands(self.root).get(gate_name, "")
            if not command:
                raise PolierError(f"no command for gate '{gate_name}': pass command or list it in docs/quality.md")
            board = board_mod.load_board(self.root, strict=False) or {}
            exclusive: List[str] = []
            for entry in board.get("tasks") or []:
                if isinstance(entry, dict) and entry.get("id") == task:
                    exclusive = [v for v in (entry.get("exclusive") or []) if isinstance(v, str)]
                    break
            infra = list(board_mod.resources(board)["infra_patterns"])
            result = gate_mod.run_gate(command, task, gate_name, self.root, shell=True,
                                       timeout=int(arguments.get("timeout") or 1800),
                                       exclusive=exclusive, infra_patterns=infra)
            if runs_mod.enabled(self.root):
                try:
                    record = result["record_path"].relative_to(result["root"]).as_posix()
                    runs_mod.record_gate(self.root, task, gate_name, result.get("result"), record)
                except Exception:  # noqa: BLE001 - a gate must not fail because of its record
                    pass
            return {
                "result": result.get("result"),
                "exit_code": result.get("exit_code"),
                "record": str(result.get("record_path")),
                "log": str(result.get("log_path")),
                "summary": gate_mod.summary(result, tail=10, max_errors=10),
            }
        if name == "polier_claim":
            if not task:
                raise PolierError("task is required")
            return claims_mod.take(self.root, task, harness="claude-code",
                                   session=_text(arguments.get("session")) or "mcp")
        if name == "polier_release":
            if not task:
                raise PolierError("task is required")
            return {"task": task, "released": claims_mod.release(self.root, task,
                                                                 _text(arguments.get("session")) or None)}
        raise PolierError(f"unknown tool {name}")


def _error(message: str, code: int = -32602) -> Dict[str, Any]:
    return {"code": code, "message": message}


def handle(server: Server, message: Dict[str, Any]):
    """One JSON-RPC message → the response dict, or None for notifications."""
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}
    response: Dict[str, Any] = {"jsonrpc": "2.0"}
    if request_id is not None:
        response["id"] = request_id
    if method == "initialize":
        result: Any = {"protocolVersion": params.get("protocolVersion") or PROTOCOL,
                       "capabilities": {"tools": {}}, "serverInfo": SERVER}
    elif method in ("notifications/initialized", "initialized"):
        return None
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": server.tools()}
    elif method == "tools/call":
        name = _text(params.get("name"))
        try:
            value = server.call(name, params.get("arguments") or {})
            result = {"content": [{"type": "text", "text": json.dumps(value, indent=2, ensure_ascii=False, default=str)}],
                      "isError": False}
        except (PolierError, KeyError, ValueError) as exc:
            result = {"content": [{"type": "text", "text": f"error: {exc}"}], "isError": True}
        except Exception as exc:  # noqa: BLE001 - report, keep the server alive
            result = {"content": [{"type": "text", "text": f"internal error: {exc}"}], "isError": True}
    else:
        if request_id is None:
            return None
        response["error"] = _error(f"unknown method {method}", -32601)
        return response
    if request_id is None:
        return None
    response["result"] = result
    return response


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Polier MCP server (stdio JSON-RPC).")
    parser.add_argument("--root", default=".", help="project folder (default: .)")
    parser.add_argument("--read-only", action="store_true", help="refuse every write tool")
    args = parser.parse_args(argv)
    server = Server(Path(args.root).resolve(), read_only=args.read_only)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if not isinstance(message, dict):
            continue
        response = handle(server, message)
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
