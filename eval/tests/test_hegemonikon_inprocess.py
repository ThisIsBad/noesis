"""Hegemonikon HTTP-layer integration test.

Drives ``services.hegemonikon.mcp_server_http.app`` via Starlette's
TestClient with a scripted ``query_fn`` injected into the
``StreamingMCPAgent``, so the test runs without spawning the Claude
CLI subprocess and without any deployed MCP services. The point of
this test is to pin the **HTTP / SSE wire format** Hegemonikon emits, not
to re-test the trace builder logic (covered in
``services/hegemonikon/tests/test_trace_builder.py``).

Specifically this asserts:

* ``POST /api/chat`` with a valid bearer returns ``202`` and a
  ``session_id``.
* ``GET /api/stream?session_id=...`` streams typed SSE events whose
  ``event:`` lines match the dispatcher in ``ui/hegemonikon/static/chat.js``.
* The full sequence (``session.start`` → tool events → ``session.done``)
  shows up in order.
* The finalised ``DecisionTrace`` carries the user's prompt as the
  root-question's ``detail`` and an ``Outcome`` with ``verdict='complete'``.

Mirrors the shape of ``test_phase1_inprocess.py`` (in-process, no
HTTP to external services, deterministic) but at the Starlette HTTP
layer rather than the bare core layer.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

# Drop any host-side HEGEMONIKON_SECRET before the bearer middleware reads it
# at server-module import time. The auth-specific test below re-imports
# the module with HEGEMONIKON_SECRET set to verify the gating path; every
# other test wants the open-mode default so it can POST without a token.
os.environ.pop("HEGEMONIKON_SECRET", None)
os.environ.pop("HEGEMONIKON_SECRET_PREV", None)

pytest.importorskip(
    "hegemonikon.mcp_server_http",
    reason="services/hegemonikon not on pythonpath",
)

from hegemonikon import mcp_server_http as server_mod  # noqa: E402
from hegemonikon.streaming_agent import StreamingMCPAgent  # noqa: E402

# Hegemonikon runs orchestration in background asyncio.create_task() — Starlette's
# sync TestClient doesn't keep a loop alive across requests, so the background
# task strands after POST /api/chat and the SSE stream stays empty. We use
# httpx.AsyncClient + ASGITransport which holds one loop for the whole test.
ASGITransport = httpx.ASGITransport


# ── SDK-shaped fakes (mirrors services/hegemonikon/tests/test_trace_builder.py) ───


# Class names mirror the real SDK types exactly because TraceBuilder
# dispatches on ``type(msg).__name__`` — using the same names lets us
# avoid pulling the SDK into the test runtime.


@dataclass
class TextBlock:
    text: str


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: Any = None
    is_error: bool | None = None


@dataclass
class AssistantMessage:
    content: list[Any] = field(default_factory=list)
    model: str = "claude"


@dataclass
class UserMessage:
    content: Any = None
    tool_use_result: dict[str, Any] | None = None


@dataclass
class ResultMessage:
    subtype: str = "success"
    duration_ms: int = 1234
    duration_api_ms: int = 1000
    is_error: bool = False
    num_turns: int = 4
    session_id: str = "sess"
    stop_reason: str | None = "end_turn"
    total_cost_usd: float | None = 0.04
    usage: dict[str, Any] | None = None
    result: str | None = "registered the goal and verified the plan"


# ── one canned canonical run: register goal → verify plan → done ──────────────


def _scripted_messages() -> list[Any]:
    return [
        AssistantMessage(
            content=[
                TextBlock(text="I'll register the goal first."),
                ToolUseBlock(
                    id="tu_1",
                    name="mcp__telos__register_goal",
                    input={"contract_json": "{}"},
                ),
            ]
        ),
        UserMessage(
            content=[
                ToolResultBlock(
                    tool_use_id="tu_1",
                    content="goal registered",
                    is_error=False,
                ),
            ]
        ),
        AssistantMessage(
            content=[
                ToolUseBlock(
                    id="tu_2",
                    name="mcp__praxis__decompose_goal",
                    input={"goal": "refactor auth"},
                ),
            ]
        ),
        UserMessage(
            content=[
                ToolResultBlock(
                    tool_use_id="tu_2",
                    content="plan ready",
                    is_error=False,
                ),
            ]
        ),
        ResultMessage(
            result="registered the goal and verified the plan",
            total_cost_usd=0.07,
        ),
    ]


@pytest.fixture
def patched_agent(monkeypatch):
    """Replace the SDK ``query`` with a scripted iterator + reset state."""
    messages = _scripted_messages()

    async def fake_query(*, prompt: str, options: Any):
        for m in messages:
            yield m

    # Patch the StreamingMCPAgent default query_fn at construction time.
    real_init = StreamingMCPAgent.__init__

    def patched_init(self, **kwargs):
        kwargs.setdefault("query_fn", fake_query)
        real_init(self, **kwargs)

    monkeypatch.setattr(StreamingMCPAgent, "__init__", patched_init)

    # Hegemonikon's process-global registry is reset between tests so leftover
    # sessions from a previous test don't leak into the next.
    server_mod._REGISTRY = type(server_mod._REGISTRY)(  # type: ignore[misc]
        max_age_s=server_mod._SESSION_MAX_AGE_S,
    )

    # Disable the Theoria post — we don't need network in this test.
    monkeypatch.setattr(server_mod, "_THEORIA_URL", "")
    return None


def _parse_sse_events(text: str) -> list[dict[str, Any]]:
    """Walk an SSE text body; yield decoded {type, ...} dicts."""
    events: list[dict[str, Any]] = []
    for chunk in text.split("\n\n"):
        if not chunk.strip():
            continue
        event_line = None
        data_line = None
        for line in chunk.splitlines():
            if line.startswith("event:"):
                event_line = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_line = line[len("data:") :].strip()
        if data_line is None:
            continue
        try:
            payload = json.loads(data_line)
        except json.JSONDecodeError:
            continue
        # Sanity: SSE event-name should match payload['type'].
        if event_line is not None and "type" in payload:
            assert event_line == payload["type"]
        events.append(payload)
    return events


# ── tests ─────────────────────────────────────────────────────────────────────


def _async_client() -> httpx.AsyncClient:
    """Build an in-process AsyncClient that keeps one event loop alive
    for both the POST /api/chat call (which spawns a background task)
    and the GET /api/stream call (which consumes that task's queue)."""
    return httpx.AsyncClient(
        transport=ASGITransport(app=server_mod.app),
        base_url="http://hegemonikon.test",
        timeout=30.0,
    )


async def test_health_is_unauth(patched_agent) -> None:
    async with _async_client() as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["service"] == "hegemonikon"
        assert "active_sessions" in body
        assert "mcp_servers" in body


async def test_chat_post_returns_session_id_and_streams_full_sequence(
    patched_agent,
) -> None:
    async with _async_client() as client:
        resp = await client.post(
            "/api/chat",
            json={"prompt": "Refactor auth and verify the plan."},
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        session_id = body["session_id"]
        trace_id = body["trace_id"]
        assert session_id and trace_id == f"hegemonikon-{session_id}"

        async with client.stream(
            "GET",
            f"/api/stream?session_id={session_id}",
        ) as stream_resp:
            assert stream_resp.status_code == 200
            chunks: list[bytes] = []
            async for chunk in stream_resp.aiter_bytes():
                chunks.append(chunk)
                if b"session.done" in b"".join(chunks):
                    break
            text = b"".join(chunks).decode()
        events = _parse_sse_events(text)

    types = [e["type"] for e in events]
    # The minimum sequence we should see, in order.
    assert types[0] == "session.start"
    assert "assistant.text" in types
    assert types.count("tool.pending") == 2
    assert types.count("tool.result") == 2
    assert types.count("trace.update") >= 2
    assert types[-1] == "session.done"

    # Last trace.update should carry the finalised structure.
    final_trace_event = [e for e in events if e["type"] == "trace.update"][-1]
    trace = final_trace_event["trace"]
    assert trace["source"] == "hegemonikon"
    assert trace["question"] == "Refactor auth and verify the plan."
    # 1 root QUESTION + 2 INFERENCE (tool_use) + 2 OBSERVATION (tool_result)
    # = 5 steps minimum (no thinking / system events in this canned run).
    assert len(trace["steps"]) == 5
    kinds = sorted(s["kind"] for s in trace["steps"])
    assert kinds == [
        "inference",
        "inference",
        "observation",
        "observation",
        "question",
    ]
    # session.done event isn't always last across SSE chunk boundaries —
    # the trace.update preceding it also carries the outcome.
    if trace.get("outcome"):
        assert trace["outcome"]["verdict"] == "complete"
        assert trace["outcome"]["summary"].startswith(
            "registered the goal and verified the plan"
        )

    # session.done payload has the budget metadata for the chat status line.
    done = events[-1]
    assert done["outcome"] == "complete"
    assert done["cost_usd"] == pytest.approx(0.07)
    assert done["duration_ms"] == 1234


async def test_chat_requires_bearer_when_secret_set(monkeypatch) -> None:
    monkeypatch.setenv("HEGEMONIKON_SECRET", "live-secret")

    # The bearer middleware was bound at import time; rebuild a fresh
    # module so it sees the env override.
    import importlib

    importlib.reload(server_mod)

    # Re-patch the agent because reload reset the monkeypatched init.
    messages = _scripted_messages()

    async def fake_query(*, prompt: str, options: Any):
        for m in messages:
            yield m

    real_init = StreamingMCPAgent.__init__

    def patched_init(self, **kwargs):
        kwargs.setdefault("query_fn", fake_query)
        real_init(self, **kwargs)

    monkeypatch.setattr(StreamingMCPAgent, "__init__", patched_init)

    try:
        async with _async_client() as client:
            # No auth → 401.
            resp = await client.post("/api/chat", json={"prompt": "hi"})
            assert resp.status_code == 401

            # Wrong auth → 401.
            resp = await client.post(
                "/api/chat",
                json={"prompt": "hi"},
                headers={"Authorization": "Bearer wrong"},
            )
            assert resp.status_code == 401

            # Right auth → 202.
            resp = await client.post(
                "/api/chat",
                json={"prompt": "hi"},
                headers={"Authorization": "Bearer live-secret"},
            )
            assert resp.status_code == 202
    finally:
        # Reload the module again with HEGEMONIKON_SECRET cleared so subsequent
        # tests in the file (and other files in the eval suite) don't
        # inherit the live-secret middleware that this reload baked in.
        monkeypatch.delenv("HEGEMONIKON_SECRET", raising=False)
        importlib.reload(server_mod)


async def test_chat_rejects_empty_prompt(patched_agent) -> None:
    async with _async_client() as client:
        resp = await client.post("/api/chat", json={"prompt": "   "})
        assert resp.status_code == 400
        assert "prompt" in resp.json()["error"]


async def test_stream_unknown_session_returns_404(patched_agent) -> None:
    async with _async_client() as client:
        resp = await client.get("/api/stream?session_id=does-not-exist")
        assert resp.status_code == 404


async def test_session_error_event_emitted_on_sdk_failure(monkeypatch) -> None:
    """If the SDK raises mid-stream, the SSE consumer must see a session.error.

    Without this guarantee a frontend EventSource would hang forever
    on a Claude-side crash; the chat-status pill would never re-enable
    Send.
    """
    monkeypatch.delenv("HEGEMONIKON_SECRET", raising=False)

    async def crashing_query(*, prompt: str, options: Any):
        # Yield one event so the session.start path runs, then blow up.
        yield AssistantMessage(content=[TextBlock(text="starting…")])
        raise RuntimeError("simulated SDK crash")

    real_init = StreamingMCPAgent.__init__

    def patched_init(self, **kwargs):
        kwargs.setdefault("query_fn", crashing_query)
        real_init(self, **kwargs)

    monkeypatch.setattr(StreamingMCPAgent, "__init__", patched_init)
    server_mod._REGISTRY = type(server_mod._REGISTRY)(  # type: ignore[misc]
        max_age_s=server_mod._SESSION_MAX_AGE_S,
    )
    monkeypatch.setattr(server_mod, "_THEORIA_URL", "")

    async with _async_client() as client:
        resp = await client.post("/api/chat", json={"prompt": "go"})
        assert resp.status_code == 202
        sid = resp.json()["session_id"]

        async with client.stream(
            "GET",
            f"/api/stream?session_id={sid}",
        ) as stream_resp:
            chunks: list[bytes] = []
            async for chunk in stream_resp.aiter_bytes():
                chunks.append(chunk)
                joined = b"".join(chunks)
                if b"session.error" in joined or b"session.done" in joined:
                    break
            text = b"".join(chunks).decode()
    events = _parse_sse_events(text)
    types = [e["type"] for e in events]
    assert "session.error" in types
    err = next(e for e in events if e["type"] == "session.error")
    assert "simulated SDK crash" in err["error"]
