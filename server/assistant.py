"""The assistant session runner (2.4): one headless agent turn per question.

The dashboard composes a read-only briefing (``core.assistant.build_prompt``),
starts a normal provider session with the ``assistant`` role and waits for its
final message in a background thread. The parsed answer and proposals are stored
in the conversation; the UI polls the conversation while the session runs and can
apply a proposal through the normal, validated API paths.

The assistant inherits the configured session provider (Claude Code by default)
and therefore the same local login. It has no task and the project hooks stay
active, so it cannot write files outside the guard's rules; the prompt also
forbids changes.
"""
from __future__ import annotations

import datetime as dt
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from core import assistant as assistant_mod
from core.errors import PolierError

from .sessions import SessionManager


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class AssistantManager:
    def __init__(self, root, sessions: SessionManager, bus=None) -> None:
        self.root = Path(root).resolve()
        self.sessions = sessions
        self.bus = bus

    # -- conversations -----------------------------------------------------
    def list(self):
        return assistant_mod.list_conversations(self.root)

    def get(self, conversation_id: str) -> Dict[str, Any]:
        return assistant_mod.load(self.root, conversation_id)

    def delete(self, conversation_id: str) -> Dict[str, Any]:
        conversation = assistant_mod.load(self.root, conversation_id)
        pending = conversation.get("pending") or {}
        if pending.get("session"):
            try:
                self.sessions.stop(str(pending["session"]))
            except KeyError:
                pass
        return assistant_mod.delete(self.root, conversation_id)

    def cancel(self, conversation_id: str) -> Dict[str, Any]:
        conversation = assistant_mod.load(self.root, conversation_id)
        pending = conversation.get("pending") or {}
        if pending.get("session"):
            try:
                self.sessions.stop(str(pending["session"]))
            except KeyError:
                pass
            conversation["pending"] = None
            assistant_mod.save(self.root, conversation)
        return conversation

    # -- chat --------------------------------------------------------------
    def start(self, message: str, conversation_id: Optional[str] = None) -> Dict[str, Any]:
        message = (message or "").strip()
        if len(message) < 2:
            raise PolierError("the question is empty")
        if len(message) > 8000:
            raise PolierError("the question is too long (max 8000 characters)")
        if not (self.root / "board.json").is_file():
            raise PolierError("no board.json; the assistant needs a planned project")
        if conversation_id:
            conversation = assistant_mod.load(self.root, conversation_id)
        else:
            conversation = assistant_mod.create(self.root)
        if conversation.get("pending"):
            raise PolierError("this conversation still has a running answer")
        prompt = assistant_mod.build_prompt(self.root, conversation, message)
        conversation = assistant_mod.append_message(
            self.root, str(conversation["id"]), {"role": "user", "content": message})
        session = self.sessions.start(role="assistant", prompt=prompt)
        conversation["pending"] = {"session": session["id"], "status": "running",
                                   "started": session.get("started")}
        conversation = assistant_mod.save(self.root, conversation)
        self._publish(conversation)
        thread = threading.Thread(target=self._watch,
                                  args=(str(conversation["id"]), str(session["id"])),
                                  daemon=True)
        thread.start()
        return conversation

    def _watch(self, conversation_id: str, session_id: str) -> None:
        deadline = time.time() + 60 * 30
        final: Dict[str, Any] = {}
        while time.time() < deadline:
            try:
                final = self.sessions.get(session_id)
            except KeyError:
                break
            if final.get("status") not in ("starting", "running"):
                break
            time.sleep(0.4)
        text = str(final.get("last_message") or "").strip()
        if not text:
            try:
                log = self.sessions.log(session_id).get("text") or ""
            except KeyError:
                log = ""
            lines = [line for line in log.splitlines()
                     if not line.startswith("[") and line.strip()]
            text = "\n".join(lines[-40:]).strip()
        status = final.get("status") or "failed"
        parsed = assistant_mod.parse_answer(text) if text else {"answer": "", "proposals": []}
        answer = parsed.get("answer") or (
            "The assistant session finished without an answer." if status == "done"
            else f"The assistant session {status} without an answer.")
        try:
            conversation = assistant_mod.load(self.root, conversation_id)
            conversation["messages"].append({
                "at": _now(), "role": "assistant", "content": answer,
                "proposals": parsed.get("proposals") or [],
                "session": session_id, "status": status,
            })
            conversation["pending"] = None
            assistant_mod.save(self.root, conversation)
            self._publish(conversation)
        except Exception:  # noqa: BLE001 - a failed store write must not crash the server
            pass

    def _publish(self, conversation: Dict[str, Any]) -> None:
        if self.bus is not None:
            self.bus.publish("assistant", {"conversation": conversation.get("id"),
                                           "pending": conversation.get("pending"),
                                           "messages": len(conversation.get("messages") or [])})
