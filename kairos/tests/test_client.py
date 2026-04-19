import time
from typing import Any, Optional

import httpx
import pytest

from kairos.client import KairosClient, current_span_id, current_trace_id


class _RecordingClient:
    """Minimal httpx.Client stand-in capturing POST payloads."""

    def __init__(self, *, raise_exc: Optional[Exception] = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._raise = raise_exc
        self.closed = False

    def post(self, url: str, *, json: dict[str, Any]) -> Any:
        self.calls.append({"url": url, "json": json})
        if self._raise is not None:
            raise self._raise
        return None

    def close(self) -> None:
        self.closed = True


def test_span_yields_trace_id_and_emits():
    http = _RecordingClient()
    client = KairosClient(base_url="http://k", service="mneme", _http=http)
    with client.span("store_memory") as trace_id:
        assert isinstance(trace_id, str) and trace_id
    assert len(http.calls) == 1
    payload = http.calls[0]["json"]
    assert http.calls[0]["url"] == "http://k/spans"
    assert payload["service"] == "mneme"
    assert payload["operation"] == "store_memory"
    assert payload["trace_id"] == trace_id
    assert payload["parent_span_id"] is None
    assert payload["success"] is True
    assert payload["duration_ms"] >= 0.0
    assert payload["metadata"] == {}


def test_nested_spans_share_trace_and_link_parent():
    http = _RecordingClient()
    client = KairosClient(base_url="http://k", service="mneme", _http=http)
    with client.span("outer") as outer_trace:
        outer_span = current_span_id()
        with client.span("inner") as inner_trace:
            assert inner_trace == outer_trace
            assert current_trace_id() == outer_trace
            assert current_span_id() != outer_span
    # Inner emits first (finally runs on exit), outer second.
    assert len(http.calls) == 2
    inner_payload = http.calls[0]["json"]
    outer_payload = http.calls[1]["json"]
    assert inner_payload["operation"] == "inner"
    assert outer_payload["operation"] == "outer"
    assert inner_payload["trace_id"] == outer_payload["trace_id"]
    assert inner_payload["parent_span_id"] == outer_span
    assert outer_payload["parent_span_id"] is None


def test_contextvars_cleared_after_span():
    http = _RecordingClient()
    client = KairosClient(base_url="http://k", service="s", _http=http)
    assert current_trace_id() is None
    assert current_span_id() is None
    with client.span("op"):
        assert current_trace_id() is not None
        assert current_span_id() is not None
    assert current_trace_id() is None
    assert current_span_id() is None


def test_disabled_client_no_http_no_emit():
    client = KairosClient(base_url=None, service="s")
    assert client.disabled is True
    with client.span("op") as trace_id:
        assert isinstance(trace_id, str)
    # No transport was created; close() is a no-op.
    client.close()


def test_disabled_via_flag_still_tracks_contextvars():
    client = KairosClient(base_url="http://k", service="s", disabled=True)
    assert client.disabled is True
    with client.span("op"):
        assert current_trace_id() is not None


def test_emit_failure_is_swallowed():
    http = _RecordingClient(raise_exc=httpx.ConnectError("refused"))
    client = KairosClient(base_url="http://k", service="s", _http=http)
    with client.span("op"):
        pass
    assert len(http.calls) == 1  # attempted


def test_exception_in_block_marks_failure_and_reraises():
    http = _RecordingClient()
    client = KairosClient(base_url="http://k", service="s", _http=http)
    with pytest.raises(RuntimeError):
        with client.span("op"):
            raise RuntimeError("boom")
    assert len(http.calls) == 1
    assert http.calls[0]["json"]["success"] is False


def test_duration_ms_reflects_elapsed_time():
    http = _RecordingClient()
    client = KairosClient(base_url="http://k", service="s", _http=http)
    with client.span("op"):
        time.sleep(0.02)
    duration = http.calls[0]["json"]["duration_ms"]
    assert duration >= 15.0  # loose bound to avoid flakiness


def test_metadata_passed_through():
    http = _RecordingClient()
    client = KairosClient(base_url="http://k", service="s", _http=http)
    with client.span("op", metadata={"k": "v"}):
        pass
    assert http.calls[0]["json"]["metadata"] == {"k": "v"}


def test_close_closes_http():
    http = _RecordingClient()
    client = KairosClient(base_url="http://k", service="s", _http=http)
    client.close()
    assert http.closed is True


def test_base_url_trailing_slash_normalised():
    http = _RecordingClient()
    client = KairosClient(base_url="http://k/", service="s", _http=http)
    with client.span("op"):
        pass
    assert http.calls[0]["url"] == "http://k/spans"
