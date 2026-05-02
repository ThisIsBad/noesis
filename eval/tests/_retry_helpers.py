"""Test-time retry for Railway mid-session MCP session drops.

Cold-start failures during the SSE handshake are already retried inside
``mcp_session`` (see test_phase1_e2e.py / conftest.py). What that helper
*doesn't* cover is the other transient Railway failure mode: the
container restarts *after* the handshake, so the next ``call_tool`` POST
to ``/messages/?session_id=X`` returns 404 and the MCP SDK raises
``McpError("Connection closed")``. The handshake retry can't catch this
because the error fires mid-session — the ``async with`` has already
yielded to the test body.

The fix is narrow by design: re-run the whole test (opening a fresh SSE
session each time) when, and only when, the failure matches one of those
two patterns. Any other exception — validation mismatches, server 500s,
plain assertion errors — surfaces immediately so real regressions stay
visible. Apply via::

    @retry_on_transient_mcp_error()
    async def test_durchstich_...(fixture, ...): ...

Default is two retries (three total attempts) with 2 s / 4 s backoff —
matches the cold-start helper so a single flake burns roughly the same
budget either way.
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import httpx
from mcp.shared.exceptions import McpError

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def _is_mid_session_drop_leaf(exc: BaseException) -> bool:
    """A single exception is a mid-session Railway drop iff it's one of:

    * ``McpError`` whose message contains ``"Connection closed"`` —
      raised by ``ClientSession.send_request`` after the server drops
      the JSON-RPC channel.
    * ``httpx.HTTPStatusError`` returning 404 on a ``/messages/?session_id=``
      URL — the POST the SDK makes after the handshake, which Railway
      now answers with 404 because the session_id is no longer known.
    """
    if isinstance(exc, McpError) and "Connection closed" in str(exc):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 404 and "/messages/" in str(exc.request.url)
    return False


def _is_mid_session_drop(exc: BaseException) -> bool:
    """Unwrap ``BaseExceptionGroup`` so anyio-wrapped failures match too."""
    if _is_mid_session_drop_leaf(exc):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_is_mid_session_drop(e) for e in exc.exceptions)
    return False


def retry_on_transient_mcp_error(
    max_attempts: int = 3, backoff: float = 2.0
) -> Callable[[F], F]:
    """Re-run an async test on Railway mid-session session drops.

    ``max_attempts`` is the total number of attempts (default 3 → two
    retries). ``backoff`` is the initial sleep in seconds; each retry
    doubles it. Non-transient errors re-raise immediately, so coverage
    of real regressions is unaffected.
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = backoff
            for attempt in range(max_attempts):
                try:
                    return await fn(*args, **kwargs)
                except BaseException as exc:
                    if attempt < max_attempts - 1 and _is_mid_session_drop(exc):
                        await asyncio.sleep(delay)
                        delay *= 2
                        continue
                    raise
            raise RuntimeError(  # pragma: no cover — loop always returns or raises
                "retry_on_transient_mcp_error: exhausted retry loop without "
                "returning — this is a bug in the decorator, not the test."
            )

        return wrapper  # type: ignore[return-value]

    return decorator
