"""Unit tests for the cold-start retry helper.

The previous implementation missed every real Railway 502/ConnectTimeout
because ``sse_client`` raises those inside an anyio TaskGroup — the
helper received a ``BaseExceptionGroup`` wrapping the retryable leaf,
but the isinstance check only inspected the top-level exception, so the
retry path never fired and every cold-start killed CI.

These tests pin the new contract:

1. Bare retryable leaves (502 status, ConnectError, ConnectTimeout,
   ReadTimeout) are retryable.
2. Retryable leaves wrapped in a BaseExceptionGroup are retryable.
3. Nested groups (group of groups) are retryable if any leaf matches.
4. Non-retryable exceptions (404, ValueError, mypy-style logic bugs)
   stay non-retryable even when wrapped.
"""

from __future__ import annotations

import httpx
import pytest

from tests.test_phase1_e2e import _is_retryable

# Pure-logic tests — no deployed services needed. The `unit` marker
# opts them into the default `pytest -m unit` job in .github/workflows/eval.yml.
pytestmark = pytest.mark.unit


def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.test/sse")
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError(f"HTTP {code}", request=request, response=response)


@pytest.mark.parametrize("code", [502, 503, 504])
def test_bare_retryable_status_is_retryable(code: int) -> None:
    assert _is_retryable(_status_error(code))


@pytest.mark.parametrize("code", [400, 401, 404, 500, 418])
def test_bare_non_retryable_status_is_not_retryable(code: int) -> None:
    assert not _is_retryable(_status_error(code))


def test_bare_connect_error_is_retryable() -> None:
    assert _is_retryable(httpx.ConnectError("refused"))


def test_bare_connect_timeout_is_retryable() -> None:
    assert _is_retryable(httpx.ConnectTimeout("timed out"))


def test_bare_read_timeout_is_retryable() -> None:
    assert _is_retryable(httpx.ReadTimeout("timed out"))


def test_bare_value_error_is_not_retryable() -> None:
    assert not _is_retryable(ValueError("logic bug"))


def test_exception_group_with_retryable_leaf_is_retryable() -> None:
    """The original bug: sse_client wraps the 502 in a TaskGroup exception."""
    group = BaseExceptionGroup("handshake failed", [_status_error(502)])
    assert _is_retryable(group)


def test_exception_group_with_connect_timeout_is_retryable() -> None:
    group = BaseExceptionGroup("handshake failed", [httpx.ConnectTimeout("timed out")])
    assert _is_retryable(group)


def test_nested_exception_groups_are_unwrapped() -> None:
    inner = BaseExceptionGroup("inner", [_status_error(503)])
    outer = BaseExceptionGroup("outer", [inner])
    assert _is_retryable(outer)


def test_exception_group_with_only_non_retryable_is_not_retryable() -> None:
    group = BaseExceptionGroup(
        "logic failure", [ValueError("oops"), _status_error(404)]
    )
    assert not _is_retryable(group)


def test_exception_group_is_retryable_if_any_leaf_matches() -> None:
    """Mixed group: one ValueError, one 502 — still retryable."""
    group = BaseExceptionGroup("mixed", [ValueError("oops"), _status_error(502)])
    assert _is_retryable(group)
