"""End-to-end trace propagation across simulated service boundaries.

Demonstrates the header-based propagation contract:

1. Service A opens a span, issues an outbound request.
2. It injects the current trace context via ``inject_headers``.
3. Service B pulls the context out via ``extract_trace_context``,
   adopts it with ``continue_trace``, and opens its own span.
4. Both services' ``KairosClient`` instances emit spans to a shared
   in-memory core (no HTTP — we wire the POSTs directly to
   ``KairosCore.record_span``).
5. Querying ``KairosCore.get_trace`` returns both spans with the
   correct trace_id and parent-child linkage.

The test doubles stand in for an httpx.Client so we can assert on
exactly what gets emitted without spinning up a real server.
"""
from __future__ import annotations

from typing import Any

import pytest

from kairos.client import (
    KairosClient,
    current_trace_id,
    extract_trace_context,
    inject_headers,
)
from kairos.core import KairosCore


class _KairosTransport:
    """Routes KairosClient emits straight into a shared KairosCore."""

    def __init__(self, core: KairosCore) -> None:
        self._core = core
        self.closed = False

    def post(self, url: str, *, json: dict[str, Any]) -> None:
        assert url.endswith("/spans")
        self._core.record_span(
            service=json["service"],
            operation=json["operation"],
            trace_id=json["trace_id"],
            span_id=json.get("span_id"),
            parent_span_id=json.get("parent_span_id"),
            duration_ms=json.get("duration_ms"),
            success=json.get("success"),
            metadata=json.get("metadata") or {},
        )

    def close(self) -> None:
        self.closed = True


def test_trace_context_round_trips_through_headers() -> None:
    """Core invariant: inject then extract yields the original pair."""
    core = KairosCore()
    transport = _KairosTransport(core)
    client = KairosClient(base_url="http://k", service="a", _http=transport)

    with client.span("outer"):
        headers = inject_headers({"Content-Type": "application/json"})
        trace_id, parent_span_id = extract_trace_context(headers)
        assert trace_id == current_trace_id()
        assert parent_span_id is not None


def test_extract_is_case_insensitive() -> None:
    trace, parent = extract_trace_context({
        "x-kairos-trace-id": "t1",
        "X-Kairos-Parent-Span-Id": "s1",
    })
    assert trace == "t1"
    assert parent == "s1"


def test_extract_returns_none_when_headers_absent() -> None:
    trace, parent = extract_trace_context({"Content-Type": "text/plain"})
    assert trace is None
    assert parent is None


def test_inject_noop_when_no_active_trace() -> None:
    out = inject_headers({"x": "y"})
    assert out == {"x": "y"}


def test_cross_service_propagation_assembles_full_trace() -> None:
    """Service A → Service B propagates trace_id and parent span.

    After the flow we expect two spans in the store: one from A
    (``a_op``) with no parent, and one from B (``b_op``) whose
    ``parent_span_id`` is A's active span at the moment it made the
    call. Both share the same ``trace_id``.
    """
    core = KairosCore()
    client_a = KairosClient(
        base_url="http://k", service="svc_a", _http=_KairosTransport(core),
    )
    client_b = KairosClient(
        base_url="http://k", service="svc_b", _http=_KairosTransport(core),
    )

    def service_b_handler(inbound_headers: dict[str, str]) -> None:
        trace_id, parent_span_id = extract_trace_context(inbound_headers)
        with client_b.continue_trace(trace_id, parent_span_id):
            with client_b.span("b_op"):
                pass

    with client_a.span("a_op"):
        headers = inject_headers()
        service_b_handler(headers)

    # Both services emit into the same core; extract the trace.
    spans = core.get_recent()
    assert len(spans) == 2

    # Both spans share a trace_id.
    trace_ids = {s.trace_id for s in spans}
    assert len(trace_ids) == 1
    (trace_id,) = trace_ids

    by_op = {s.operation: s for s in spans}
    assert set(by_op) == {"a_op", "b_op"}
    assert by_op["a_op"].service == "svc_a"
    assert by_op["b_op"].service == "svc_b"
    assert by_op["a_op"].parent_span_id is None
    # Child's parent matches A's span_id (the span A emitted, whose
    # id was injected as the parent_span for B).
    assert by_op["b_op"].parent_span_id == by_op["a_op"].span_id

    # And get_trace must return both.
    trace = core.get_trace(trace_id)
    assert len(trace) == 2


def test_continue_trace_is_noop_when_both_values_are_none() -> None:
    core = KairosCore()
    client = KairosClient(
        base_url="http://k", service="svc", _http=_KairosTransport(core),
    )
    assert current_trace_id() is None
    with client.continue_trace(None, None):
        with client.span("op") as trace_id:
            # Fresh trace_id because nothing was adopted.
            assert trace_id is not None
    spans = core.get_recent()
    assert len(spans) == 1
    assert spans[0].parent_span_id is None


def test_continue_trace_adopts_trace_id_even_without_parent() -> None:
    """Downstream can continue a trace whose inbound headers omit the
    parent_span (e.g. the caller started a fresh trace with no parent).
    """
    core = KairosCore()
    client = KairosClient(
        base_url="http://k", service="svc", _http=_KairosTransport(core),
    )
    with client.continue_trace("inbound-trace", None):
        with client.span("op") as trace_id:
            assert trace_id == "inbound-trace"
    spans = core.get_recent()
    assert len(spans) == 1
    assert spans[0].trace_id == "inbound-trace"
    assert spans[0].parent_span_id is None


@pytest.mark.parametrize("enabled", [True, False])
def test_inject_works_regardless_of_client_enabled_state(enabled: bool) -> None:
    """Header injection reads from contextvars, so it works even when
    the client's HTTP transport is disabled. Otherwise services would
    silently drop cross-service trace context in dev/test."""
    core = KairosCore()
    transport = _KairosTransport(core) if enabled else None
    client = KairosClient(
        base_url="http://k" if enabled else None,
        service="svc",
        disabled=not enabled,
        _http=transport,
    )
    with client.span("op"):
        headers = inject_headers()
        assert "X-Kairos-Trace-Id" in headers
