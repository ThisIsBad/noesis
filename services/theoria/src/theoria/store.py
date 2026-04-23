"""In-memory decision-trace store with optional JSONL persistence.

Kept deliberately simple: no external deps, safe for single-process
use. For multi-process deployments, back this with Mneme once the
episodic-memory service lands.
"""

from __future__ import annotations

import json
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Iterable

from theoria.models import DecisionTrace


class TraceStore:
    """Append-only trace store with most-recent-first listing."""

    def __init__(self, persist_path: Path | None = None) -> None:
        self._traces: "OrderedDict[str, DecisionTrace]" = OrderedDict()
        self._lock = threading.RLock()
        self._persist_path = persist_path
        if persist_path is not None:
            persist_path.parent.mkdir(parents=True, exist_ok=True)
            if persist_path.exists():
                self._load_from_disk()

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
            return self._traces.pop(trace_id, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._traces.clear()
            if self._persist_path is not None and self._persist_path.exists():
                self._persist_path.unlink()

    def __len__(self) -> int:
        with self._lock:
            return len(self._traces)
