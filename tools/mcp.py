#!/usr/bin/env python3
"""Polier as an MCP server: connect your own Claude Code (or any MCP host).

Usage:
    python3 tools/mcp.py [--root .] [--read-only]

Add it to Claude Code with:

    claude mcp add polier -- python3 /path/to/polier/tools/mcp.py --root .

Tools (JSON-RPC ``tools/call``):
    polier_snapshot   whole project snapshot (tasks, dispatch, stages, counts)
    polier_tasks      every task with status, gates, tokens
    polier_task       one task with brief, review, gates and events
    polier_dispatch   next wave, running, blocked, conflicts
    polier_show       board status against the run record
    polier_activity   newest-first event feed
    polier_approvals  approval records (pending by default)
    polier_claims     live claims
    polier_state_set  lead-only status transition (needs a lead session)
    polier_gate       run one gate and return its record summary
    polier_claim      take the claim for a task
    polier_release    release the claim of a task

The server speaks newline-delimited JSON-RPC 2.0 on stdio (MCP stdio
transport), runs on the Python standard library only, and writes nothing but
what the called tools do.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import approvals as approvals_mod  # noqa: E402
from core import board as board_mod  # noqa: E402
from core import claims as claims_mod  # noqa: E402
from core import dashboard as dashboard_mod  # noqa: E402
from core import filters as filters_mod  # noqa: E402
from core import gate as gate_mod  # noqa: E402
from core import inbox as inbox_mod  # noqa: E402
from core import runs as runs_mod  # noqa: E402
from core import runtime as runtime_mod  # noqa: E402
from core import settings as settings_mod  # noqa: E402
from core import state as state_mod  # noqa: E402
from core import views as views_mod  # noqa: E402
from core import worklog as worklog_mod  # noqa: E402
from core.errors import PolierError  # noqa: E402
from core.gates import suggest_gate_commands  # noqa: E402

PROTOCOL = "2024-11-05"
SERVER = {"name": "polier", "version": "2.1.0"}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


class Server:
    def __init__(self, root: Path, read_only: bool = False) -> None:
        self.root = root
        self.read_only = read_only

    # -- tools -------------------------------------------------------------
    def tools(self) -> List[Dict[str, Any]]:
        return [
            {"name": "polier_snapshot", "description": "Whole project snapshot: tasks with derived fields, dispatch, stages, counts, git.",
             "inputSchema": {"type": "object", "properties": {}}},
            {"name": "polier_tasks", "description": "Every task with status, stage, gates, tokens and review verdict.",
             "inputSchema": {"type": "object", "properties": {}}},
            {"name": "polier_task", "description": "One task with brief, review, gate records and run events.",
             "inputSchema": {"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]}},
            {"name": "polier_dispatch", "description": "Next wave, running tasks, blocked tasks and scope conflicts.",
             "inputSchema": {"type": "object", "properties": {}}},
            {"name": "polier_show", "description": "Board status against the run record, gates, review and approvals.",
             "inputSchema": {"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]}},
            {"name": "polier_activity", "description": "Newest-first feed of run events and approvals.",
             "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
            {"name": "polier_approvals", "description": "Approval records; pending by default.",
             "inputSchema": {"type": "object", "properties": {"status": {"type": "string"}}}},
            {"name": "polier_claims", "description": "Live claims of this repository.",
             "inputSchema": {"type": "object", "properties": {}}},
            {"name": "polier_state_set", "description": "Lead-only status transition through the state machine.",
             "inputSchema": {"type": "object", "properties": {
                 "task": {"type": "string"}, "status": {"type": "string"},
                 "note": {"type": "string"}}, "required": ["task", "status"]}},
            {"name": "polier_gate", "description": "Run one gate, write its evidence record and return the summary.",
             "inputSchema": {"type": "object", "properties": {
                 "task": {"type": "string"}, "name": {"type": "string"},
                 "command": {"type": "string"}, "timeout": {"type": "integer"}},
                 "required": ["task", "name"]}},
            {"name": "polier_settings", "description": "Committed dashboard settings: features, labels, defaults and the current feature flags.",
             "inputSchema": {"type": "object", "properties": {}}},
            {"name": "polier_views", "description": "Built-in and saved task views (filters, grouping, sorting).",
             "inputSchema": {"type": "object", "properties": {}}},
            {"name": "polier_worklog", "description": "Actual effort from runs, gates and sessions, for one task or the whole project.",
             "inputSchema": {"type": "object", "properties": {"task": {"type": "string"}}}},
            {"name": "polier_me", "description": "Your Work: my tasks, reviews, approvals, claims and sessions.",
             "inputSchema": {"type": "object", "properties": {}}},
            {"name": "polier_inbox", "description": "Actionable inbox items (approvals, failed gates, blocked tasks, budget, reviews).",
             "inputSchema": {"type": "object", "properties": {"unread": {"type": "boolean"}, "limit": {"type": "integer"}}}},
            {"name": "polier_inbox_read", "description": "Mark inbox items read; use all=true to mark the current inbox read, reset=true to clear the read state.",
             "inputSchema": {"type": "object", "properties": {
                 "ids": {"type": "array", "items": {"type": "string"}}, "all": {"type": "boolean"},
                 "reset": {"type": "boolean"}}}},
            {"name": "polier_claim", "description": "Take the claim for a task (harness/session optional).",
             "inputSchema": {"type": "object", "properties": {
                 "task": {"type": "string"}, "session": {"type": "string"}}, "required": ["task"]}},
            {"name": "polier_release", "description": "Release the claim of a task.",
             "inputSchema": {"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]}},
        ]

    def call(self, name: str, arguments: Dict[str, Any]) -> Any:
        arguments = arguments if isinstance(arguments, dict) else {}
        task = _text(arguments.get("task"))
        if name == "polier_snapshot":
            snapshot = dashboard_mod.snapshot(self.root)
            return {
                "project": snapshot["project"],
                "counts": snapshot["counts"],
                "stages": [{key: stage.get(key) for key in ("id", "title", "owner_decision", "complete", "tasks_open")}
                           for stage in snapshot["stages"]],
                "dispatch": snapshot["dispatch"],
                "approvals_pending": snapshot["approvals"]["pending"],
                "git": snapshot["git"],
                "tasks": [{key: view.get(key) for key in ("id", "title", "status", "stage", "owner", "tokens")}
                          for view in snapshot["tasks"]],
            }
        if name == "polier_tasks":
            snapshot = dashboard_mod.snapshot(self.root)
            return [{key: view.get(key) for key in (
                "id", "title", "status", "stage", "stage_title", "owner", "complexity",
                "gates", "gates_passed", "gates_missing", "tokens", "attempt", "review",
                "claim", "blocked_reason", "next_status")} for view in snapshot["tasks"]]
        if name == "polier_task":
            if not task:
                raise PolierError("task is required")
            return dashboard_mod.task_detail(self.root, task)
        if name == "polier_dispatch":
            return dashboard_mod.snapshot(self.root)["dispatch"]
        if name == "polier_show":
            if not task:
                raise PolierError("task is required")
            return state_mod.status_of(self.root, task)
        if name == "polier_activity":
            limit = arguments.get("limit")
            return dashboard_mod.activity(self.root, int(limit) if limit else 120)
        if name == "polier_approvals":
            records = approvals_mod.load_all(self.root)
            status = _text(arguments.get("status")) or "pending"
            return [record for record in records if record.get("status") == status]
        if name == "polier_claims":
            return claims_mod.live_claims(self.root)
        if name == "polier_state_set":
            self._guard()
            status = _text(arguments.get("status"))
            if not task or not status:
                raise PolierError("task and status are required")
            return state_mod.set_status(self.root, task, status, actor="lead",
                                        note=arguments.get("note"))
        if name == "polier_gate":
            self._guard()
            gate_name = _text(arguments.get("name"))
            if not task or not gate_name:
                raise PolierError("task and name are required")
            command = _text(arguments.get("command"))
            if not command:
                command = self._gate_commands().get(gate_name, "")
            if not command:
                raise PolierError(f"no command configured for gate '{gate_name}'")
            board = board_mod.load_board(self.root, strict=False) or {}
            exclusive: List[str] = []
            infra: List[str] = []
            for entry in board.get("tasks") or []:
                if isinstance(entry, dict) and entry.get("id") == task:
                    exclusive = [value for value in (entry.get("exclusive") or []) if isinstance(value, str)]
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
        if name == "polier_settings":
            value = settings_mod.load(self.root, strict=False)
            return {
                "settings": value,
                "features": settings_mod.features(value),
                "labels": settings_mod.label_list(value),
                "me": settings_mod.me(value),
                "errors": settings_mod.errors(value),
            }
        if name == "polier_views":
            me = settings_mod.me(settings_mod.load(self.root, strict=False))
            return {"builtin": filters_mod.builtin_views(me),
                    "saved": views_mod.load_all(self.root),
                    "all": views_mod.all_views(self.root, me)}
        if name == "polier_worklog":
            if task:
                try:
                    detail = dashboard_mod.task_detail(self.root, task)
                except KeyError:
                    raise PolierError(f"unknown task {task}")
                return detail["worklog"]
            snapshot = dashboard_mod.snapshot(self.root)
            return worklog_mod.project_worklog(self.root, snapshot["tasks"])
        if name == "polier_me":
            snapshot = dashboard_mod.snapshot(self.root)
            return inbox_mod.your_work(self.root, snapshot=snapshot)
        if name == "polier_inbox":
            snapshot = dashboard_mod.snapshot(self.root)
            summary = inbox_mod.inbox_summary(self.root, snapshot=snapshot)
            items = summary["items"]
            if arguments.get("unread"):
                items = [item for item in items if not item.get("read")]
            limit = arguments.get("limit")
            if isinstance(limit, int) and limit > 0:
                items = items[:limit]
            return {"items": items, "counts": summary["counts"]}
        if name == "polier_inbox_read":
            self._guard()
            ids = arguments.get("ids") if isinstance(arguments.get("ids"), list) else []
            return inbox_mod.mark_read(self.root, [str(item) for item in ids],
                                       all_items=bool(arguments.get("all")),
                                       reset=bool(arguments.get("reset")))
        if name == "polier_claim":
            self._guard()
            if not task:
                raise PolierError("task is required")
            return claims_mod.take(self.root, task, harness="claude-code",
                                   session=_text(arguments.get("session")) or "mcp")
        if name == "polier_release":
            self._guard()
            if not task:
                raise PolierError("task is required")
            return {"task": task, "released": claims_mod.release(self.root, task,
                                                                 _text(arguments.get("session")) or None)}
        raise PolierError(f"unknown tool {name}")

    def _guard(self) -> None:
        if self.read_only:
            raise PolierError("this MCP server runs read-only")

    def _gate_commands(self) -> Dict[str, str]:
        config = runtime_mod.read_json(runtime_mod.runtime_dir(self.root) / "config.json")
        commands = {**suggest_gate_commands(self.root), **(config.get("gate_commands") or {})}
        return {key: value for key, value in commands.items() if isinstance(key, str) and isinstance(value, str)}


def _error(message: str, code: int = -32602) -> Dict[str, Any]:
    return {"code": code, "message": message}


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
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}
        response: Dict[str, Any] = {"jsonrpc": "2.0"}
        if request_id is not None:
            response["id"] = request_id
        if method == "initialize":
            result = {"protocolVersion": params.get("protocolVersion") or PROTOCOL,
                      "capabilities": {"tools": {}},
                      "serverInfo": SERVER}
        elif method in ("notifications/initialized", "initialized"):
            continue
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": server.tools()}
        elif method == "tools/call":
            name = _text((params or {}).get("name"))
            arguments = (params or {}).get("arguments") or {}
            try:
                value = server.call(name, arguments)
                result = {"content": [{"type": "text", "text": json.dumps(value, indent=2, ensure_ascii=False)}],
                          "isError": False}
            except (PolierError, KeyError, ValueError) as exc:
                result = {"content": [{"type": "text", "text": f"error: {exc}"}], "isError": True}
            except Exception as exc:  # noqa: BLE001 - report, keep the server alive
                result = {"content": [{"type": "text", "text": f"internal error: {exc}"}], "isError": True}
        else:
            if request_id is None:
                continue
            response["error"] = _error(f"unknown method {method}", -32601)
            print(json.dumps(response), flush=True)
            continue
        if request_id is None:
            continue
        response["result"] = result
        print(json.dumps(response, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
