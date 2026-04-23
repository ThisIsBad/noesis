from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

from theoria.models import DecisionTrace, ReasoningStep, StepKind
from theoria.server import make_server
from theoria.store import TraceStore


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live_server():
    store = TraceStore()
    port = _free_port()
    server, _ = make_server(host="127.0.0.1", port=port, store=store)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # Give the server a moment to bind.
    time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    try:
        yield base, store
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def _get(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")


def _post(url: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = json.dumps(body).encode("utf-8") if body is not None else b"{}"
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")


def test_health_endpoint(live_server) -> None:
    base, _ = live_server
    status, body = _get(f"{base}/health")
    assert status == 200
    assert body["ok"] is True


def test_samples_load_and_list(live_server) -> None:
    base, store = live_server
    status, body = _post(f"{base}/api/samples/load")
    assert status == 200
    loaded = body["loaded"]
    assert loaded >= 4

    status, body = _get(f"{base}/api/traces")
    assert status == 200
    ids = [t["id"] for t in body["traces"]]
    assert "sample-logos-policy-block" in ids
    assert "sample-z3-proof" in ids
    assert len(store) == loaded == len(ids)


def test_post_custom_trace_round_trip(live_server) -> None:
    base, _ = live_server
    trace = DecisionTrace(
        id="custom",
        title="Custom",
        question="?",
        source="test",
        kind="custom",
        root="q",
        steps=[ReasoningStep(id="q", kind=StepKind.QUESTION, label="Q")],
    )
    status, body = _post(f"{base}/api/traces", trace.to_dict())
    assert status == 201
    assert body["id"] == "custom"

    status, body = _get(f"{base}/api/traces/custom")
    assert status == 200
    assert body["title"] == "Custom"


def test_get_unknown_trace_returns_404(live_server) -> None:
    base, _ = live_server
    status, _ = _get(f"{base}/api/traces/does-not-exist")
    assert status == 404


def test_static_index_is_served(live_server) -> None:
    base, _ = live_server
    with urllib.request.urlopen(f"{base}/") as resp:
        body = resp.read().decode()
    assert "<title>Theoria" in body


def test_static_traversal_is_blocked(live_server) -> None:
    base, _ = live_server
    req = urllib.request.Request(f"{base}/static/../../../../etc/passwd")
    try:
        resp = urllib.request.urlopen(req)
        # Some servers normalize the path and 404; both are acceptable defenses.
        assert resp.status in (403, 404)
    except urllib.error.HTTPError as exc:
        assert exc.code in (403, 404)


def test_clear_removes_all_traces(live_server) -> None:
    base, store = live_server
    _post(f"{base}/api/samples/load")
    assert len(store) > 0
    status, body = _post(f"{base}/api/clear")
    assert status == 200
    assert body["ok"] is True
    assert len(store) == 0
