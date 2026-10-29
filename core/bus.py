"""A tiny in-process publish/subscribe bus for the dashboard (2.0).

The CLI and the state files stay the source of truth; the bus only fans out
notifications to connected dashboards. Subscribers get their own bounded queue,
so a slow browser tab never blocks a writer: when the queue is full the oldest
event is dropped and a `lag` event marks the gap.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Any, Dict, List, Optional

DEFAULT_CAPACITY = 500


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Subscription:
    """One subscriber queue. Use it as a context manager or close() it yourself."""

    def __init__(self, bus: "EventBus", capacity: int = DEFAULT_CAPACITY) -> None:
        self._bus = bus
        self._queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=capacity)
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._bus._remove(self)

    def __enter__(self) -> "Subscription":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def get(self, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
        """The next event, or None on timeout. Raises nothing on close."""
        if self._closed:
            return None
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        while True:
            try:
                items.append(self._queue.get_nowait())
            except queue.Empty:
                return items

    def _put(self, event: Dict[str, Any]) -> None:
        if self._closed:
            return
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            # Drop the oldest event, mark the gap, retry once.
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait({"t": now(), "topic": "lag", "data": {}})
                self._queue.put_nowait(event)
            except queue.Full:
                pass


class EventBus:
    """Thread-safe fan-out of small JSON events (`topic`, `t`, `data`)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: List[Subscription] = []
        self._seq = 0
        self._counts: Dict[str, int] = {}

    def subscribe(self) -> Subscription:
        sub = Subscription(self)
        with self._lock:
            self._subs.append(sub)
        return sub

    def _remove(self, sub: Subscription) -> None:
        with self._lock:
            if sub in self._subs:
                self._subs.remove(sub)

    def publish(self, topic: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        event = {"seq": 0, "t": now(), "topic": topic, "data": data or {}}
        with self._lock:
            self._seq += 1
            event["seq"] = self._seq
            self._counts[topic] = self._counts.get(topic, 0) + 1
            subs = list(self._subs)
        for sub in subs:
            sub._put(event)
        return event

    def publish_many(self, events: List[Dict[str, Any]]) -> None:
        for event in events:
            self.publish(str(event.get("topic", "message")), event.get("data") or {})

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {"seq": self._seq, "subscribers": len(self._subs), "topics": dict(self._counts)}
