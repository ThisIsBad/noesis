"""In-memory session registry.

A ``Session`` ties together one running Claude conversation with the
asyncio task driving it, the SSE event queue, and the in-flight
``DecisionTrace``. This is intentionally a single-process registry —
Console's MVP scope is "interactive recorded sessions on one box,"
not "horizontally scaled chat backend." When the second use case
matters, swap this for Mneme or Redis.

Lifecycle:

    POST /api/chat
        → create_session() returns a fresh Session with an empty queue
        → background task starts running StreamingMCPAgent.chat(...)
        → task pushes events into Session.queue
    GET /api/stream?session_id=...
        → consumes Session.queue.get() forever, streams as SSE
    background task finishes
        → posts final DecisionTrace to Theoria
        → pushes ``done`` event to queue
        → Session is GC'd after the SSE consumer disconnects

Sessions are timed out + cleaned up by the periodic sweeper in
``mcp_server_http.py`` so a forgotten browser tab doesn't pin memory
forever.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Session:
    """One running chat session."""

    session_id: str
    prompt: str
    created_at: float = field(default_factory=time.monotonic)
    queue: asyncio.Queue[dict[str, Any]] = field(
        default_factory=lambda: asyncio.Queue(maxsize=1024)
    )
    task: asyncio.Task[None] | None = None
    finished: bool = False
    # Final DecisionTrace dict once the task completes; None until then.
    final_trace: dict[str, Any] | None = None
    error: str | None = None

    def is_alive(self, max_age_s: float) -> bool:
        return (time.monotonic() - self.created_at) < max_age_s


class SessionRegistry:
    """Process-local map ``session_id → Session``.

    All accessors are sync because asyncio.Queue is the synchronisation
    primitive for the streaming side; the registry itself is just a
    dict guarded by an asyncio.Lock so create/remove don't race on the
    sweeper.
    """

    def __init__(self, *, max_sessions: int = 64, max_age_s: float = 3600) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()
        self._max_sessions = max_sessions
        self._max_age_s = max_age_s

    async def create(self, prompt: str) -> Session:
        async with self._lock:
            self._evict_old_locked()
            if len(self._sessions) >= self._max_sessions:
                raise RuntimeError(
                    f"too many active sessions ({len(self._sessions)})"
                )
            sid = uuid.uuid4().hex
            session = Session(session_id=sid, prompt=prompt)
            self._sessions[sid] = session
            return session

    async def get(self, session_id: str) -> Session | None:
        async with self._lock:
            return self._sessions.get(session_id)

    async def remove(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)

    async def sweep(self) -> int:
        """Drop expired sessions; return count removed."""
        async with self._lock:
            return self._evict_old_locked()

    def _evict_old_locked(self) -> int:
        # Caller holds self._lock.
        stale = [
            sid for sid, s in self._sessions.items()
            if not s.is_alive(self._max_age_s)
        ]
        for sid in stale:
            session = self._sessions.pop(sid, None)
            if session and session.task is not None and not session.task.done():
                session.task.cancel()
        return len(stale)

    @property
    def size(self) -> int:
        return len(self._sessions)
