"""In-memory decision-trace store with optional JSONL persistence.

Kept deliberately simple: no external deps, safe for single-process
use. For multi-process deployments, back this with Mneme once the
episodic-memory service lands.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable

from theoria.models import DecisionTrace

logger = logging.getLogger("theoria.store")


class TraceStore:
    """Append-only trace store with most-recent-first listing."""

    def __init__(self, persist_path: Path | None = None) -> None:
        self._traces: "OrderedDict[str, DecisionTrace]" = OrderedDict()
        self._lock = threading.RLock()
        self._listeners: list["queue.Queue[dict[str, Any]]"] = []
        self._listener_lock = threading.Lock()
        self._persist_path = persist_path
        if persist_path is not None:
            persist_path.parent.mkdir(parents=True, exist_ok=True)
            if persist_path.exists():
                self._load_from_disk()

    # ---- pub/sub -----------------------------------------------------

    def subscribe(self, max_queue: int = 256) -> "queue.Queue[dict[str, Any]]":
        """Return a Queue that receives one event per put()/delete()/clear()."""
        q: "queue.Queue[dict[str, Any]]" = queue.Queue(maxsize=max_queue)
        with self._listener_lock:
            self._listeners.append(q)
        return q

    def unsubscribe(self, q: "queue.Queue[dict[str, Any]]") -> None:
        with self._listener_lock:
            try:
                self._listeners.remove(q)
            except ValueError:
                pass

    def _broadcast(self, event: dict[str, Any]) -> None:
        with self._listener_lock:
            listeners = list(self._listeners)
        for q in listeners:
            try:
                q.put_nowait(event)
            except queue.Full:
                # Slow consumer — drop the event rather than block producers.
                logger.debug("dropping SSE event for slow listener")

    def _load_from_disk(self) -> None:
        assert self._persist_path is not None
        with self._persist_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                    trace = DecisionTrace.from_dict(payload)
                except (ValueError, json.JSONDecodeError):
                    continue
                self._traces[trace.id] = trace

    def _append_to_disk(self, trace: DecisionTrace) -> None:
        if self._persist_path is None:
            return
        with self._persist_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(trace.to_dict(), sort_keys=True))
            fh.write("\n")

    def put(self, trace: DecisionTrace) -> DecisionTrace:
        trace.validate()
        with self._lock:
            # Re-insert at end to preserve most-recent-first ordering on list()
            self._traces.pop(trace.id, None)
            self._traces[trace.id] = trace
            self._append_to_disk(trace)
        self._broadcast({"type": "trace.put", "id": trace.id, "trace": trace.to_dict()})
        return trace

    def put_many(self, traces: Iterable[DecisionTrace]) -> int:
        count = 0
        for trace in traces:
            self.put(trace)
            count += 1
        return count

    def get(self, trace_id: str) -> DecisionTrace | None:
        with self._lock:
            return self._traces.get(trace_id)

    def list(self, limit: int | None = None) -> list[DecisionTrace]:
        with self._lock:
            items = list(reversed(self._traces.values()))
        if limit is not None:
            items = items[:limit]
        return items

    def delete(self, trace_id: str) -> bool:
        with self._lock:
            removed = self._traces.pop(trace_id, None) is not None
        if removed:
            self._broadcast({"type": "trace.delete", "id": trace_id})
        return removed

    def clear(self) -> None:
        with self._lock:
            self._traces.clear()
            if self._persist_path is not None and self._persist_path.exists():
                self._persist_path.unlink()
        self._broadcast({"type": "trace.clear"})

    def __len__(self) -> int:
        with self._lock:
            return len(self._traces)
