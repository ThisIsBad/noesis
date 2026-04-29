"""Tests for the Kairos live-fetch integration.

A small stub HTTP server impersonates Kairos so we can exercise:
    1. The ``KairosClient`` against a real socket.
    2. The ``GET /api/kairos/traces/{id}`` Theoria endpoint end-to-end.
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from theoria.kairos_client import KairosClient, KairosError
from theoria.server import make_server
from theoria.store import TraceStore


# ---------------------------------------------------------------------------
# Stub Kairos server
# ---------------------------------------------------------------------------

_SPANS_FIXTURE: list[dict] = [
    {
        "trace_id": "t-real",
        "span_id": "a",
        "parent_span_id": None,
        "service": "logos",
        "operation": "certify_claim",
        "duration_ms": 12.3,
        "success": True,
        "metadata": {"claim_type": "propositional"},
    },
    {
        "trace_id": "t-real",
        "span_id": "b",
        "parent_span_id": "a",
        "service": "mneme",
        "operation": "recall",
        "duration_ms": 4.1,
        "success": True,
        "metadata": {"hits": "3"},
    },
    {
        "trace_id": "t-real",
        "span_id": "c",
        "parent_span_id": "b",
        "service": "praxis",
        "operation": "commit_step",
        "duration_ms": 30.0,
        "success": False,
        "metadata": {"err": "timeout"},
    },
]


class _StubKairosHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/traces/t-real"):
            self._write_json(HTTPStatus.OK, _SPANS_FIXTURE)
        elif self.path.startswith("/traces/"):
            self._write_json(HTTPStatus.OK, [])
        elif self.path == "/boom":
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "boom"})
        else:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def _write_json(self, status: int, payload) -> None:
        body = json.dumps(payload).encode()
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def stub_kairos():
    port = _free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _StubKairosHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


# ---------------------------------------------------------------------------
# KairosClient
# ---------------------------------------------------------------------------


def test_client_fetch_trace_parses_spans(stub_kairos) -> None:
    client = KairosClient(stub_kairos)
    spans = client.fetch_trace("t-real")
    assert [s.span_id for s in spans] == ["a", "b", "c"]
    assert spans[2].success is False
    assert spans[1].metadata == {"hits": "3"}


def test_client_returns_empty_list_for_unknown_trace(stub_kairos) -> None:
    client = KairosClient(stub_kairos)
    spans = client.fetch_trace("nope")
    assert spans == []


def test_client_raises_on_kairos_5xx(stub_kairos) -> None:
    # The stub treats anything not in /traces/* as 404. Instead poke a
    # path we explicitly 500 on via a custom client base.
    client = KairosClient(stub_kairos)
    with pytest.raises(KairosError, match="HTTP 500"):
        client._get_json(f"{stub_kairos}/boom")


def test_client_raises_on_connection_refused() -> None:
    # Pick an unused port and immediately rebind nothing.
    port = _free_port()
    client = KairosClient(f"http://127.0.0.1:{port}", timeout=0.5)
    with pytest.raises(KairosError, match="connection"):
        client.fetch_trace("any")


# ---------------------------------------------------------------------------
# End-to-end: Theoria /api/kairos/traces/{id}
# ---------------------------------------------------------------------------


@pytest.fixture
def theoria_server(stub_kairos):
    store = TraceStore()
    port = _free_port()
    server, _ = make_server(
        host="127.0.0.1",
        port=port,
        store=store,
        kairos=KairosClient(stub_kairos),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}", store
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def test_live_kairos_endpoint_returns_decision_trace(theoria_server) -> None:
    base, store = theoria_server
    with urllib.request.urlopen(f"{base}/api/kairos/traces/t-real") as resp:
        payload = json.loads(resp.read())
    assert payload["source"] == "kairos"
    assert payload["outcome"]["verdict"] == "failed"  # c succeeded=False
    # The live fetch MUST NOT persist into Theoria's store.
    assert len(store) == 0


def test_live_kairos_endpoint_404_for_missing_trace(theoria_server) -> None:
    base, _ = theoria_server
    try:
        urllib.request.urlopen(f"{base}/api/kairos/traces/does-not-exist")
        assert False, "should have raised HTTPError"
    except urllib.error.HTTPError as exc:
        assert exc.code == 404


def test_live_kairos_endpoint_502_on_kairos_failure(theoria_server) -> None:
    base, _ = theoria_server
    # Point Theoria at a dead Kairos by rebuilding the server fixture.
    # Simpler: re-create a client pointed at a closed port and exercise the path.
    port = _free_port()
    dead = KairosClient(f"http://127.0.0.1:{port}", timeout=0.5)
    store = TraceStore()
    server, _ = make_server(
        host="127.0.0.1",
        port=_free_port(),
        store=store,
        kairos=dead,
    )
    import threading as _t

    th = _t.Thread(target=server.serve_forever, daemon=True)
    th.start()
    time.sleep(0.05)
    try:
        host, port = server.server_address
        url = f"http://{host}:{port}/api/kairos/traces/any"
        try:
            urllib.request.urlopen(url)
            assert False, "should have raised HTTPError"
        except urllib.error.HTTPError as exc:
            assert exc.code == 502
            body = json.loads(exc.read())
            assert "Kairos fetch failed" in body["error"]
    finally:
        server.shutdown()
        server.server_close()
        th.join(timeout=1)
