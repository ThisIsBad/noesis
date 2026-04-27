"""Console HTTP server.

Two endpoints + /health:

    POST /api/chat        accepts {prompt} (and optional {max_budget_usd})
                          returns {session_id} immediately; the actual
                          Claude run happens in a background asyncio task.
    GET  /api/stream      Server-Sent Events stream for one session_id.
                          Each event is a JSON-encoded dict produced by
                          TraceBuilder; see trace_builder.py for shapes.

The Console is intentionally NOT a FastMCP server — it doesn't expose
tools to other Claude sessions. It's an *orchestrator-and-recorder*:
it accepts a prompt over HTTP, runs Claude with all eight Noesis MCP
servers wired in, captures the resulting DecisionTrace, and pushes it
to Theoria's existing /api/traces endpoint when the session ends.

Security: bearer-middleware-gated like every other Noesis service.
``/health`` is exempt; ``/`` and ``/static/*`` are exempt so a browser
can fetch the chat shell before authenticating.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import mimetypes
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, AsyncIterator

from noesis_clients.auth import bearer_middleware
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .sessions import SessionRegistry
from .streaming_agent import StreamingMCPAgent, noesis_mcp_servers_from_env
from .trace_builder import TraceBuilder

logging.basicConfig(
    level=os.getenv("CONSOLE_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("console")

# ── boot config ─────────────────────────────────────────────────────────────

_MAX_BUDGET_USD = float(os.getenv("CONSOLE_MAX_BUDGET_USD", "0.25"))
_MODEL = os.getenv("CONSOLE_MODEL", "claude-sonnet-4-6")
_MAX_TURNS = int(os.getenv("CONSOLE_MAX_TURNS", "12"))
_THEORIA_URL = os.getenv("THEORIA_URL", "")  # empty = don't post finals
_THEORIA_SECRET = os.getenv("THEORIA_SECRET", "")
_SESSION_MAX_AGE_S = float(os.getenv("CONSOLE_SESSION_MAX_AGE_S", "3600"))

_secret_set = bool(os.getenv("CONSOLE_SECRET"))
_anthropic_set = bool(os.getenv("ANTHROPIC_API_KEY"))
log.info(
    "console boot: port=%s secret_set=%s anthropic_key_set=%s "
    "max_budget_usd=%s theoria_url_set=%s",
    os.getenv("PORT", "8000"),
    _secret_set, _anthropic_set, _MAX_BUDGET_USD, bool(_THEORIA_URL),
)

_SERVICES_AT_BOOT = noesis_mcp_servers_from_env()
log.info(
    "console mcp servers at boot: %s",
    sorted(_SERVICES_AT_BOOT.keys()) or "(none)",
)

_REGISTRY = SessionRegistry(max_age_s=_SESSION_MAX_AGE_S)

# ── UI assets path ──────────────────────────────────────────────────────────

# Where the UI lives. In Docker we COPY ui/console/ to /app/ui/console/;
# locally the layout is /home/user/noesis/ui/console/. The CONSOLE_UI_DIR
# env var lets you override (useful for dev or for shipping the
# Console-server without the UI assets).
_DEFAULT_UI_DIRS = (
    Path("/app/ui/console"),
    Path(__file__).resolve().parent.parent.parent.parent.parent / "ui" / "console",
)
_UI_DIR_OVERRIDE = os.getenv("CONSOLE_UI_DIR")
if _UI_DIR_OVERRIDE:
    _UI_DIR: Path | None = Path(_UI_DIR_OVERRIDE)
else:
    _UI_DIR = next((p for p in _DEFAULT_UI_DIRS if p.exists()), None)
log.info("console ui dir: %s", _UI_DIR or "(none — chat UI disabled)")


# ── HTTP handlers ───────────────────────────────────────────────────────────


async def health(_: Request) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "service": "console",
            "active_sessions": _REGISTRY.size,
            "mcp_servers": sorted(_SERVICES_AT_BOOT.keys()),
        }
    )


async def index(_: Request) -> Response:
    if _UI_DIR is None:
        return JSONResponse(
            {"error": "ui not bundled; set CONSOLE_UI_DIR to enable"},
            status_code=404,
        )
    index_path = _UI_DIR / "index.html"
    if not index_path.exists():
        return JSONResponse(
            {"error": "ui/index.html missing"}, status_code=404,
        )
    return FileResponse(str(index_path))


async def chat(request: Request) -> JSONResponse:
    body = await request.json()
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return JSONResponse({"error": "prompt required"}, status_code=400)
    max_budget = body.get("max_budget_usd")
    try:
        budget = float(max_budget) if max_budget is not None else _MAX_BUDGET_USD
    except (TypeError, ValueError):
        return JSONResponse(
            {"error": "max_budget_usd must be a number"}, status_code=400,
        )

    session = await _REGISTRY.create(prompt=prompt)
    log.info(
        "console session started: %s prompt_len=%d budget_usd=%s",
        session.session_id, len(prompt), budget,
    )

    # Refresh the MCP-server map at session-start time (not at boot)
    # so a service URL that came online late picks up automatically.
    servers = noesis_mcp_servers_from_env()
    agent = StreamingMCPAgent(
        model=_MODEL,
        mcp_servers=servers,
        max_turns=_MAX_TURNS,
        max_budget_usd=budget,
    )
    builder = TraceBuilder(session_id=session.session_id, user_prompt=prompt)
    session.task = asyncio.create_task(
        _run_session(session, agent, builder),
        name=f"console-session-{session.session_id}",
    )
    return JSONResponse(
        {"session_id": session.session_id, "trace_id": builder.trace.id},
        status_code=202,
    )


async def stream(request: Request) -> Response:
    session_id = request.query_params.get("session_id", "")
    if not session_id:
        return JSONResponse(
            {"error": "session_id query param required"}, status_code=400,
        )
    session = await _REGISTRY.get(session_id)
    if session is None:
        return JSONResponse(
            {"error": f"unknown session_id {session_id}"}, status_code=404,
        )

    async def event_stream() -> AsyncIterator[bytes]:
        # Keep alive even if Claude takes a while to emit the first message.
        emitted = 0
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        session.queue.get(), timeout=15.0,
                    )
                except asyncio.TimeoutError:
                    yield b": keepalive\n\n"
                    if session.finished:
                        break
                    continue
                yield _sse_format(event)
                emitted += 1
                if event.get("type") in {"session.done", "session.error"}:
                    break
        except Exception:
            log.exception("console sse generator crashed: %s", session_id)
            raise
        finally:
            log.info(
                "console sse stream closed: %s (emitted=%d)",
                session_id, emitted,
            )

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "close",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=headers,
    )


def _sse_format(event: dict[str, Any]) -> bytes:
    payload = json.dumps(event, default=str)
    return f"event: {event.get('type', 'message')}\ndata: {payload}\n\n".encode()


# ── background task ─────────────────────────────────────────────────────────


async def _run_session(
    session: Any,
    agent: StreamingMCPAgent,
    builder: TraceBuilder,
) -> None:
    """Drive Claude → translate every SDK message into SSE + trace updates."""
    try:
        await session.queue.put(builder.start_event())
        async for msg in agent.chat(session.prompt):
            for event in builder.ingest(msg):
                await session.queue.put(event)
    except asyncio.CancelledError:
        await session.queue.put(
            {"type": "session.error", "error": "cancelled"}
        )
        raise
    except Exception as exc:
        log.exception("console session crashed: %s", session.session_id)
        session.error = f"{type(exc).__name__}: {exc}"
        await session.queue.put(
            {"type": "session.error", "error": session.error}
        )
    finally:
        session.finished = True
        session.final_trace = builder.to_dict()
        # Best-effort: post the final trace to Theoria for browse/diff.
        if _THEORIA_URL:
            await asyncio.to_thread(
                _post_to_theoria, builder.to_dict(), _THEORIA_URL, _THEORIA_SECRET,
            )


def _post_to_theoria(trace: dict[str, Any], theoria_url: str, secret: str) -> None:
    url = theoria_url.rstrip("/") + "/api/traces"
    body = json.dumps(trace).encode()
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with contextlib.closing(urllib.request.urlopen(req, timeout=10.0)) as resp:
            if resp.status >= 400:
                log.warning(
                    "console: theoria refused trace (%s): %s",
                    resp.status, resp.read()[:200],
                )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        # Don't crash the session if Theoria is down; the trace is still
        # in the SSE stream the browser already consumed.
        log.warning("console: theoria post failed: %s", exc)


# ── app + CLI entry ─────────────────────────────────────────────────────────

routes: list[Any] = [
    Route("/health", health, methods=["GET"]),
    Route("/api/chat", chat, methods=["POST"]),
    Route("/api/stream", stream, methods=["GET"]),
    Route("/", index, methods=["GET"]),
    Route("/index.html", index, methods=["GET"]),
]
if _UI_DIR is not None:
    static_dir = _UI_DIR / "static"
    if static_dir.exists():
        # Make sure JS/CSS get correct MIME types even on hosts where
        # mimetypes.init() doesn't recognise modern extensions.
        mimetypes.add_type("application/javascript", ".js")
        mimetypes.add_type("text/css", ".css")
        routes.append(
            Mount("/static", app=StaticFiles(directory=str(static_dir)))
        )

app = Starlette(routes=routes)
# Bearer-token gate — reads CONSOLE_SECRET + CONSOLE_SECRET_PREV for
# rotation. /health, /, /index.html, /static/* are exempt; the chat
# and stream APIs require auth.
app.add_middleware(
    bearer_middleware(
        "CONSOLE_SECRET",
        exempt_paths={"/health", "/", "/index.html"},
        exempt_prefixes=("/static/",),
    )
)


def main() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
