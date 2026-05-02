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
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
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


def test_stats_endpoint(live_server) -> None:
    base, _ = live_server
    _post(f"{base}/api/samples/load")
    status, body = _get(f"{base}/api/stats")
    assert status == 200
    assert body["total"] == 4
    assert set(body["by_source"]) == {"logos", "praxis", "telos"}
    assert "top_triggered_rules" in body


def test_stats_endpoint_top_n(live_server) -> None:
    base, _ = live_server
    _post(f"{base}/api/samples/load")
    status, body = _get(f"{base}/api/stats?top_n=1")
    assert status == 200
    assert len(body["top_triggered_rules"]) <= 1


def test_search_endpoint_with_step_predicate(live_server) -> None:
    base, _ = live_server
    _post(f"{base}/api/samples/load")
    status, body = _post(
        f"{base}/api/traces/search",
        {
            "any_step": [{"kind": "rule_check", "status": "triggered"}],
        },
    )
    assert status == 200
    ids = [t["id"] for t in body["traces"]]
    assert ids == ["sample-logos-policy-block"]


def test_search_endpoint_rejects_unknown_predicate_field(live_server) -> None:
    base, _ = live_server
    _post(f"{base}/api/samples/load")
    status, body = _post(
        f"{base}/api/traces/search",
        {
            "any_step": [{"kind": "note", "bogus": 1}],
        },
    )
    assert status == 400
    assert "unknown" in body["error"]


def test_list_accepts_filter_query_params(live_server) -> None:
    base, _ = live_server
    _post(f"{base}/api/samples/load")
    # Filter by source.
    status, body = _get(f"{base}/api/traces?source=logos")
    assert status == 200
    sources = {t["source"] for t in body["traces"]}
    assert sources == {"logos"}
    # Filter by verdict.
    status, body = _get(f"{base}/api/traces?verdict=block")
    assert status == 200
    assert all(t["outcome"]["verdict"] == "block" for t in body["traces"])
    # Filter by tag.
    status, body = _get(f"{base}/api/traces?tag=drift")
    assert status == 200
    assert all("drift" in t["tags"] for t in body["traces"])
    # Full-text search.
    status, body = _get(f"{base}/api/traces?q=refactor")
    assert status == 200
    titles = [t["title"].lower() for t in body["traces"]]
    assert any("auth" in title or "refactor" in title for title in titles)
    # Limit.
    status, body = _get(f"{base}/api/traces?limit=1")
    assert status == 200
    assert len(body["traces"]) == 1


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


# ---------------------------------------------------------------------------
# Export endpoint
# ---------------------------------------------------------------------------


def test_export_mermaid(live_server) -> None:
    base, _ = live_server
    _post(f"{base}/api/samples/load")
    with urllib.request.urlopen(f"{base}/api/traces/sample-logos-policy-block/export?format=mermaid") as resp:
        body = resp.read().decode()
        assert resp.status == 200
        assert resp.headers.get("Content-Type", "").startswith("text/plain")
    assert "flowchart TD" in body
    assert "classDef ok" in body


def test_export_markdown(live_server) -> None:
    base, _ = live_server
    _post(f"{base}/api/samples/load")
    with urllib.request.urlopen(f"{base}/api/traces/sample-telos-drift/export?format=markdown") as resp:
        body = resp.read().decode()
        assert resp.status == 200
        assert resp.headers.get("Content-Type", "").startswith("text/markdown")
        cd = resp.headers.get("Content-Disposition", "")
        assert cd.endswith('.md"') or cd.endswith(".md")
    assert body.startswith("# ")
    assert "```mermaid" in body
    assert "## Outcome" in body


def test_export_dot(live_server) -> None:
    base, _ = live_server
    _post(f"{base}/api/samples/load")
    with urllib.request.urlopen(f"{base}/api/traces/sample-z3-proof/export?format=dot") as resp:
        body = resp.read().decode()
    assert "digraph Trace" in body
    assert "rankdir=TB" in body


def test_export_unknown_format_returns_400(live_server) -> None:
    base, _ = live_server
    _post(f"{base}/api/samples/load")
    req = urllib.request.Request(f"{base}/api/traces/sample-z3-proof/export?format=pdf")
    try:
        urllib.request.urlopen(req)
        assert False, "should have raised HTTPError"
    except urllib.error.HTTPError as exc:
        assert exc.code == 400


def test_export_unknown_trace_returns_404(live_server) -> None:
    base, _ = live_server
    req = urllib.request.Request(f"{base}/api/traces/nope/export?format=mermaid")
    try:
        urllib.request.urlopen(req)
        assert False, "should have raised HTTPError"
    except urllib.error.HTTPError as exc:
        assert exc.code == 404


# ---------------------------------------------------------------------------
# Diff endpoint
# ---------------------------------------------------------------------------


def test_diff_endpoint_json(live_server) -> None:
    base, _ = live_server
    _post(f"{base}/api/samples/load")
    status, body = _get(f"{base}/api/traces/sample-logos-policy-block/diff/sample-z3-proof")
    assert status == 200
    assert body["a_id"] == "sample-logos-policy-block"
    assert body["b_id"] == "sample-z3-proof"
    assert "added_steps" in body and "removed_steps" in body


def test_diff_endpoint_markdown(live_server) -> None:
    base, _ = live_server
    _post(f"{base}/api/samples/load")
    with urllib.request.urlopen(
        f"{base}/api/traces/sample-logos-policy-block/diff/sample-z3-proof?format=markdown"
    ) as resp:
        assert resp.status == 200
        assert resp.headers.get("Content-Type", "").startswith("text/markdown")
        body = resp.read().decode()
    assert body.startswith("# Trace diff")


def test_diff_endpoint_missing_trace_returns_404(live_server) -> None:
    base, _ = live_server
    _post(f"{base}/api/samples/load")
    status, body = _get(f"{base}/api/traces/not-there/diff/sample-z3-proof")
    assert status == 404
    assert "not found" in body["error"]


def test_diff_endpoint_unknown_format_returns_400(live_server) -> None:
    base, _ = live_server
    _post(f"{base}/api/samples/load")
    req = urllib.request.Request(f"{base}/api/traces/sample-z3-proof/diff/sample-telos-drift?format=pdf")
    try:
        urllib.request.urlopen(req)
        assert False, "should have raised HTTPError"
    except urllib.error.HTTPError as exc:
        assert exc.code == 400


# ---------------------------------------------------------------------------
# Server-Sent Events
# ---------------------------------------------------------------------------


def test_sse_broadcasts_new_trace(live_server) -> None:
    base, _ = live_server
    events: list[str] = []
    stop = threading.Event()

    def reader() -> None:
        try:
            with urllib.request.urlopen(f"{base}/api/stream", timeout=5) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", errors="replace")
                    events.append(line)
                    if "trace.put" in line:
                        stop.set()
                        return
                    if stop.is_set():
                        return
        except (urllib.error.URLError, OSError):
            pass

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    # Give the reader a moment to establish the stream.
    time.sleep(0.15)

    trace = DecisionTrace(
        id="sse-demo",
        title="sse",
        question="?",
        source="test",
        kind="custom",
        root="q",
        steps=[ReasoningStep(id="q", kind=StepKind.QUESTION, label="Q")],
    )
    status, _ = _post(f"{base}/api/traces", trace.to_dict())
    assert status == 201

    # Wait up to 2s for the event to arrive.
    stop.wait(timeout=2.0)
    joined = "".join(events)
    assert "event: trace_put" in joined
    assert "sse-demo" in joined


def test_sse_heartbeat_establishes_stream(live_server) -> None:
    # The server should send ": connected" immediately after headers.
    base, _ = live_server
    with urllib.request.urlopen(f"{base}/api/stream", timeout=3) as resp:
        assert resp.status == 200
        assert resp.headers.get("Content-Type", "").startswith("text/event-stream")
        # Read one chunk to confirm the stream is open.
        first = resp.readline()
        assert first.startswith(b":")
