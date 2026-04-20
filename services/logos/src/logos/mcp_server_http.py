"""HTTP/SSE transport for the LogicBrain MCP server.

Designed for cloud deployment (Railway, Render, Fly.io).
The stdio server (mcp_server.py) remains unchanged for local use.

Environment variables:
    PORT               TCP port to listen on (default: 8000)
    LOGOS_SECRET       Bearer token required on every request.
                       If unset, the server accepts all connections.
                       Set this in Railway → Variables.
"""

from __future__ import annotations

import os

try:
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Mount, Route
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "HTTP dependencies not installed. Run: pip install logic-brain[http]"
    ) from exc

from logos.mcp_server import create_server

_SECRET = os.environ.get("LOGOS_SECRET", "")


def _authorized(request: Request) -> bool:
    if not _SECRET:
        return True
    return request.headers.get("Authorization", "") == f"Bearer {_SECRET}"


def create_http_app() -> Starlette:
    server = create_server()
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> Response:
        if not _authorized(request):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        async with sse.connect_sse(
            request.scope, request.receive, request._send  # type: ignore[attr-defined]
        ) as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
        return Response()

    async def healthcheck(request: Request) -> Response:
        return JSONResponse({"status": "ok", "service": "logic-brain-mcp", "version": "0.9.0"})

    return Starlette(
        routes=[
            Route("/", endpoint=healthcheck),
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ]
    )


def main() -> None:
    """Run the LogicBrain MCP server over HTTP/SSE."""
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(create_http_app(), host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
