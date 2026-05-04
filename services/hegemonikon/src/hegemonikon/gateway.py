"""Hegemonikon gateway: one MCP endpoint that proxies to the eight cognitive
services.

Why this exists
---------------
Without the gateway, every MCP client (Claude Code on the web, future agents,
other services) needs eight bearer tokens — one per backend service — which
either land in plaintext config or force a per-client secrets store. The
gateway folds that down to a single bearer (``HEGEMONIKON_SECRET``) at the
client edge. Per-service bearers stay server-side as Railway env vars
(``NOESIS_<SVC>_SECRET``) and never leave the gateway process.

Wire flow
---------
::

    Client --[Bearer HEGEMONIKON_SECRET]--> Hegemonikon /gateway/sse
                                                |
                                                | per upstream service:
                                                v
                                           SSE handshake
                                                |
            +---------------------+-------------+-------------+----- ...
            v                     v                                 v
        logos /sse            mneme /sse                       techne /sse
        + LOGOS_SECRET        + MNEME_SECRET                   + TECHNE_SECRET

Tool naming
-----------
Backend tools are exposed under the namespace ``<service>__<tool>``
(double underscore; single underscore would collide with normal
``snake_case`` method names like ``list_proven_beliefs``). So
``mneme.store_memory`` becomes ``mneme__store_memory`` for the client.

Discovery
---------
The first ``tools/list`` call triggers parallel discovery: the gateway
opens an SSE session to each configured backend, calls ``list_tools``,
namespaces the results, and caches the merged list. Backends that fail
to respond are logged and skipped — the gateway stays usable with whatever
subset is reachable. The cache survives for the gateway process lifetime;
restart Hegemonikon to pick up backend additions or schema changes.

Dispatch
--------
Each ``tools/call`` opens a fresh SSE session to the matched backend,
forwards the call, and streams the response back. Per-call connections
keep the gateway stateless and side-step the bookkeeping of long-lived
upstream sessions; the cost is one TCP/TLS handshake per call, which is
acceptable for Phase 0 throughput. Pooling is a later optimization.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, Sequence

from mcp import ClientSession, types
from mcp.client.sse import sse_client
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.responses import Response
from starlette.routing import Mount, Route
from starlette.types import Receive, Scope, Send

from .streaming_agent import NOESIS_SERVICE_NAMES

log = logging.getLogger("hegemonikon.gateway")

NAMESPACE_SEP = "__"
"""Separator between backend name and remote tool name. Double underscore
keeps tool names unambiguous against the snake_case methods most backends
expose (``list_proven_beliefs``, ``store_memory``, etc.). Changing this
later is a wire-breaking change for every connected client."""


@dataclass(frozen=True)
class BackendConfig:
    """One upstream service's connection envelope.

    ``url`` is the service base URL (without trailing ``/sse``); the gateway
    appends ``/sse`` for the handshake and ``/messages/...`` is handled by
    the SSE protocol. ``secret`` is the bearer the gateway uses to
    authenticate against this specific backend; empty string means the
    backend is configured without auth (only safe in local dev)."""

    name: str
    url: str
    secret: str


def backends_from_env(
    names: Sequence[str] = NOESIS_SERVICE_NAMES,
    *,
    env: dict[str, str] | None = None,
) -> list[BackendConfig]:
    """Discover backends from ``NOESIS_<SVC>_URL`` / ``NOESIS_<SVC>_SECRET``.

    Mirrors the env-discovery convention used by ``streaming_agent`` and
    every other Noesis component, so a Hegemonikon process configured for
    the chat surface is automatically also configured for the gateway."""
    import os

    em = env if env is not None else dict(os.environ)
    backends: list[BackendConfig] = []
    for name in names:
        url = em.get(f"NOESIS_{name.upper()}_URL")
        if not url:
            continue
        secret = em.get(f"NOESIS_{name.upper()}_SECRET", "")
        backends.append(BackendConfig(name=name, url=url, secret=secret))
    return backends


async def _list_remote_tools(b: BackendConfig) -> list[types.Tool]:
    """Open an SSE session, fetch the backend's tool manifest as-is, close.

    Returns the backend's tools with their original names (no namespacing);
    the caller adds the ``<service>__`` prefix. Returns an empty list (rather
    than raising) if the backend is unreachable so the gateway can still
    serve tools from the rest of the stack."""
    headers = {"Authorization": f"Bearer {b.secret}"} if b.secret else None
    sse_url = b.url.rstrip("/") + "/sse"
    try:
        async with AsyncExitStack() as stack:
            read, write = await stack.enter_async_context(
                sse_client(sse_url, headers=headers)
            )
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            result = await session.list_tools()
            log.info(
                "gateway discovered %d tools from %s", len(result.tools), b.name
            )
            return list(result.tools)
    except Exception as exc:
        log.warning(
            "gateway: backend %s tools/list failed (%s: %s); skipping",
            b.name,
            type(exc).__name__,
            exc,
        )
        return []


def _namespace_tools(b: BackendConfig, tools: list[types.Tool]) -> list[types.Tool]:
    """Prefix each tool's name with ``<service>__`` for client-facing exposure."""
    return [
        types.Tool(
            name=f"{b.name}{NAMESPACE_SEP}{t.name}",
            description=t.description,
            inputSchema=t.inputSchema,
        )
        for t in tools
    ]


async def _call_remote_tool(
    b: BackendConfig, tool_name: str, arguments: dict[str, Any]
) -> list[types.ContentBlock]:
    """Forward a tool call to a backend and return its content blocks.

    Raises on failure. The lower-level MCP server wraps exceptions into a
    proper error result for the client, so we don't need to catch here."""
    headers = {"Authorization": f"Bearer {b.secret}"} if b.secret else None
    sse_url = b.url.rstrip("/") + "/sse"
    async with AsyncExitStack() as stack:
        read, write = await stack.enter_async_context(
            sse_client(sse_url, headers=headers)
        )
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        result = await session.call_tool(tool_name, arguments)
        return list(result.content)


def build_gateway(backends: Sequence[BackendConfig]) -> Server:
    """Build the lower-level MCP ``Server`` that proxies to the backends.

    The returned server is ASGI-mounted by ``gateway_routes``. Tool discovery
    is lazy (first ``tools/list`` call triggers it) so server startup doesn't
    block on slow backends. The discovered manifest is cached for the process
    lifetime; restart to refresh."""
    server: Server = Server("hegemonikon-gateway")
    by_name = {b.name: b for b in backends}

    cache: dict[str, list[types.Tool]] = {}
    cache_lock = asyncio.Lock()

    async def _ensure_cache() -> list[types.Tool]:
        async with cache_lock:
            if "merged" not in cache:
                results = await asyncio.gather(
                    *(_list_remote_tools(b) for b in backends),
                    return_exceptions=False,
                )
                merged: list[types.Tool] = []
                for b, tools in zip(backends, results):
                    merged.extend(_namespace_tools(b, tools))
                cache["merged"] = merged
                log.info(
                    "gateway tool cache primed: %d tools across %d backends",
                    len(merged),
                    len(backends),
                )
            return cache["merged"]

    @server.list_tools()
    async def _handle_list_tools() -> list[types.Tool]:
        return await _ensure_cache()

    # validate_input=False because the upstream backend is the authoritative
    # validator; double-validating here would either duplicate effort or
    # diverge from upstream semantics if a backend's schema evolves while
    # the gateway's cached copy lags. Better to forward and let the upstream
    # speak for itself.
    @server.call_tool(validate_input=False)
    async def _handle_call_tool(
        name: str, arguments: dict[str, Any]
    ) -> list[types.ContentBlock]:
        if NAMESPACE_SEP not in name:
            raise ValueError(
                f"gateway: tool name {name!r} missing service prefix "
                f"(expected '<service>{NAMESPACE_SEP}<tool>')"
            )
        prefix, _, remote_name = name.partition(NAMESPACE_SEP)
        backend = by_name.get(prefix)
        if backend is None:
            raise ValueError(
                f"gateway: unknown backend service {prefix!r} "
                f"(known: {sorted(by_name)})"
            )
        log.info(
            "gateway dispatch: %s -> %s.%s args=%s",
            name,
            backend.name,
            remote_name,
            sorted(arguments.keys()),
        )
        return await _call_remote_tool(backend, remote_name, arguments)

    return server


def gateway_routes(
    server: Server, mount_prefix: str = "/gateway"
) -> list[Route | Mount]:
    """Build Starlette routes that mount the gateway under ``mount_prefix``.

    Two routes are produced:
        ``GET  {mount_prefix}/sse``        — SSE handshake / event stream
        ``POST {mount_prefix}/messages/*`` — client-to-server message channel

    The bearer middleware on the parent app gates both — clients must supply
    ``Authorization: Bearer $HEGEMONIKON_SECRET``. Per-backend bearers stay
    inside the gateway process, never on the wire to the client."""
    sse = SseServerTransport(f"{mount_prefix}/messages/")

    async def handle_sse(scope: Scope, receive: Receive, send: Send) -> Response:
        async with sse.connect_sse(scope, receive, send) as streams:
            await server.run(
                streams[0],
                streams[1],
                server.create_initialization_options(),
            )
        return Response()

    return [
        Route(f"{mount_prefix}/sse", endpoint=handle_sse, methods=["GET"]),
        Mount(f"{mount_prefix}/messages/", app=sse.handle_post_message),
    ]
