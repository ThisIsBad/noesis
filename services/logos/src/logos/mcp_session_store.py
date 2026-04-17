"""Stateful Z3 session storage for MCP tool calls."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import TypeVar

from logos.exceptions import SessionError
from logos.orchestrator import ProofOrchestrator
from logos.z3_session import CheckResult, Z3Session

T = TypeVar("T")

ORCHESTRATOR_STORE: dict[str, ProofOrchestrator] = {}


class UnknownSessionError(SessionError):
    """Raised when a requested session does not exist."""


class ExpiredSessionError(SessionError):
    """Raised when a requested session has expired due to inactivity."""


class SessionLimitError(SessionError):
    """Raised when the store has reached its concurrent session limit."""


@dataclass
class _SessionEntry:
    session: Z3Session
    last_access: float
    next_assertion_index: int = 0


class Z3SessionStore:
    """In-memory store for stateful MCP Z3 sessions."""

    def __init__(
        self,
        *,
        expiry_seconds: float = 600.0,
        max_sessions: int = 10,
        time_fn: Callable[[], float] | None = None,
        timeout_ms: int = 30000,
    ) -> None:
        self.expiry_seconds = expiry_seconds
        self.max_sessions = max_sessions
        self.timeout_ms = timeout_ms
        self._time_fn = time_fn or monotonic
        self._lock = Lock()
        self._sessions: dict[str, _SessionEntry] = {}

    def create(self, session_id: str) -> str:
        """Create a named session."""
        session_id = _validate_session_id(session_id)
        now = self._time_fn()
        with self._lock:
            self._cleanup_expired_locked(now)
            if session_id in self._sessions:
                raise ValueError(f"Session '{session_id}' already exists")
            if len(self._sessions) >= self.max_sessions:
                raise SessionLimitError(f"Session limit reached ({self.max_sessions})")
            self._sessions[session_id] = _SessionEntry(
                session=Z3Session(timeout_ms=self.timeout_ms, track_unsat_core=True),
                last_access=now,
            )
        return session_id

    def destroy(self, session_id: str) -> None:
        """Destroy a named session."""
        session_id = _validate_session_id(session_id)
        with self._lock:
            self._cleanup_expired_locked(self._time_fn(), exclude={session_id})
            entry = self._get_entry_locked(session_id)
            entry.session.reset()
            del self._sessions[session_id]

    def declare(self, session_id: str, variables: Mapping[str, tuple[str, int | None]]) -> list[str]:
        """Declare variables in a named session."""
        names: list[str] = []

        def operation(entry: _SessionEntry) -> list[str]:
            for name, (sort, size) in variables.items():
                entry.session.declare(name, sort, size=size)
                names.append(name)
            return names

        return self._with_entry(session_id, operation)

    def assert_constraints(self, session_id: str, constraints: list[str]) -> int:
        """Assert constraints in a named session."""

        def operation(entry: _SessionEntry) -> int:
            for constraint in constraints:
                name = f"constraint_{entry.next_assertion_index}"
                entry.session.assert_constraint(constraint, name=name)
                entry.next_assertion_index += 1
            return len(constraints)

        return self._with_entry(session_id, operation)

    def check(self, session_id: str) -> CheckResult:
        """Run a satisfiability check for a named session."""
        return self._with_entry(session_id, lambda entry: entry.session.check())

    def push(self, session_id: str) -> int:
        """Push a new scope and return the new depth."""

        def operation(entry: _SessionEntry) -> int:
            entry.session.push()
            return entry.session.scope_depth

        return self._with_entry(session_id, operation)

    def pop(self, session_id: str, count: int = 1) -> int:
        """Pop scopes and return the resulting depth."""
        if count < 1:
            raise ValueError("Field 'count' must be >= 1")

        def operation(entry: _SessionEntry) -> int:
            entry.session.pop(count)
            return entry.session.scope_depth

        return self._with_entry(session_id, operation)

    def cleanup_expired(self) -> list[str]:
        """Eagerly remove expired sessions and return their ids."""
        with self._lock:
            return self._cleanup_expired_locked(self._time_fn())

    def _with_entry(self, session_id: str, operation: Callable[[_SessionEntry], T]) -> T:
        session_id = _validate_session_id(session_id)
        now = self._time_fn()
        with self._lock:
            self._cleanup_expired_locked(now, exclude={session_id})
            entry = self._get_entry_locked(session_id)
            entry.last_access = now
            result = operation(entry)
            entry.last_access = self._time_fn()
            return result

    def _get_entry_locked(self, session_id: str) -> _SessionEntry:
        entry = self._sessions.get(session_id)
        if entry is None:
            raise UnknownSessionError(f"Unknown session '{session_id}'")
        if self._time_fn() - entry.last_access > self.expiry_seconds:
            entry.session.reset()
            del self._sessions[session_id]
            raise ExpiredSessionError(f"Session '{session_id}' expired due to inactivity")
        return entry

    def _cleanup_expired_locked(self, now: float, exclude: set[str] | None = None) -> list[str]:
        ignored = exclude or set()
        expired_ids = [
            session_id
            for session_id, entry in self._sessions.items()
            if session_id not in ignored and now - entry.last_access > self.expiry_seconds
        ]
        for session_id in expired_ids:
            self._sessions[session_id].session.reset()
            del self._sessions[session_id]
        return expired_ids


def _validate_session_id(session_id: object) -> str:
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("Field 'session_id' must be a non-empty string")
    normalized = session_id.strip()
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    if any(ch not in allowed for ch in normalized):
        raise ValueError("Field 'session_id' may contain only letters, digits, '.', '_' or '-'")
    return normalized
