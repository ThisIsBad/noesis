"""Unit tests for ``retry_on_transient_mcp_error``.

Pins the narrow-by-design contract: the decorator retries *only* the two
known Railway mid-session failure patterns, and only on async tests. A
test that fails for any other reason must surface immediately so real
regressions aren't masked by silent retries.
"""
from __future__ import annotations

import httpx
import pytest
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from tests._retry_helpers import (
    _is_mid_session_drop,
    retry_on_transient_mcp_error,
)

pytestmark = pytest.mark.unit


def _mcp_error(message: str) -> McpError:
    return McpError(ErrorData(code=-32000, message=message))


def _messages_404() -> httpx.HTTPStatusError:
    request = httpx.Request(
        "POST",
        "https://svc.up.railway.app/messages/?session_id=abc123",
    )
    response = httpx.Response(404, request=request)
    return httpx.HTTPStatusError("404", request=request, response=response)


def _sse_handshake_502() -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://svc.up.railway.app/sse")
    response = httpx.Response(502, request=request)
    return httpx.HTTPStatusError("502", request=request, response=response)


# ── Leaf / group classification ───────────────────────────────────────────────

def test_connection_closed_mcp_error_is_a_drop() -> None:
    assert _is_mid_session_drop(_mcp_error("Connection closed"))


def test_other_mcp_error_is_not_a_drop() -> None:
    assert not _is_mid_session_drop(_mcp_error("validation failed"))


def test_messages_404_is_a_drop() -> None:
    assert _is_mid_session_drop(_messages_404())


def test_sse_handshake_502_is_not_a_drop() -> None:
    """Cold-start handshake failures are handled elsewhere. The mid-session
    decorator must ignore them so both layers stay narrow."""
    assert not _is_mid_session_drop(_sse_handshake_502())


def test_other_404_on_non_messages_path_is_not_a_drop() -> None:
    request = httpx.Request("GET", "https://svc.up.railway.app/health")
    response = httpx.Response(404, request=request)
    err = httpx.HTTPStatusError("404", request=request, response=response)
    assert not _is_mid_session_drop(err)


def test_drop_wrapped_in_exception_group_is_a_drop() -> None:
    group = BaseExceptionGroup(
        "anyio taskgroup", [_mcp_error("Connection closed")]
    )
    assert _is_mid_session_drop(group)


def test_drop_nested_in_group_of_groups_is_a_drop() -> None:
    inner = BaseExceptionGroup("inner", [_messages_404()])
    outer = BaseExceptionGroup("outer", [inner])
    assert _is_mid_session_drop(outer)


def test_group_with_only_non_drops_is_not_a_drop() -> None:
    group = BaseExceptionGroup(
        "mixed", [ValueError("oops"), _mcp_error("validation failed")]
    )
    assert not _is_mid_session_drop(group)


# ── Decorator behaviour ───────────────────────────────────────────────────────

async def test_decorator_returns_value_on_clean_run() -> None:
    @retry_on_transient_mcp_error()
    async def inner() -> str:
        return "ok"

    assert await inner() == "ok"


async def test_decorator_retries_on_connection_closed_then_succeeds() -> None:
    calls = {"n": 0}

    @retry_on_transient_mcp_error(max_attempts=3, backoff=0.0)
    async def inner() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise _mcp_error("Connection closed")
        return "recovered"

    assert await inner() == "recovered"
    assert calls["n"] == 2


async def test_decorator_retries_on_messages_404_then_succeeds() -> None:
    calls = {"n": 0}

    @retry_on_transient_mcp_error(max_attempts=3, backoff=0.0)
    async def inner() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _messages_404()
        return "recovered"

    assert await inner() == "recovered"
    assert calls["n"] == 3


async def test_decorator_gives_up_after_max_attempts() -> None:
    calls = {"n": 0}

    @retry_on_transient_mcp_error(max_attempts=2, backoff=0.0)
    async def inner() -> None:
        calls["n"] += 1
        raise _mcp_error("Connection closed")

    with pytest.raises(McpError, match="Connection closed"):
        await inner()
    assert calls["n"] == 2


async def test_decorator_does_not_retry_non_transient_error() -> None:
    """A plain AssertionError from a test body must surface on attempt 1."""
    calls = {"n": 0}

    @retry_on_transient_mcp_error(max_attempts=3, backoff=0.0)
    async def inner() -> None:
        calls["n"] += 1
        raise AssertionError("real regression")

    with pytest.raises(AssertionError, match="real regression"):
        await inner()
    assert calls["n"] == 1


async def test_decorator_does_not_retry_other_mcp_errors() -> None:
    """Only ``Connection closed`` MCP errors are transient — validation
    errors, tool errors, auth errors must surface immediately."""
    calls = {"n": 0}

    @retry_on_transient_mcp_error(max_attempts=3, backoff=0.0)
    async def inner() -> None:
        calls["n"] += 1
        raise _mcp_error("invalid params")

    with pytest.raises(McpError):
        await inner()
    assert calls["n"] == 1


async def test_decorator_retries_when_drop_is_wrapped_in_group() -> None:
    """anyio TaskGroup-style wrapping must not defeat the retry path."""
    calls = {"n": 0}

    @retry_on_transient_mcp_error(max_attempts=3, backoff=0.0)
    async def inner() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise BaseExceptionGroup(
                "taskgroup", [_mcp_error("Connection closed")]
            )
        return "recovered"

    assert await inner() == "recovered"
    assert calls["n"] == 2
