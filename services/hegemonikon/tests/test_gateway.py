"""Unit tests for the Hegemonikon gateway.

The tests exercise discovery + dispatch by monkey-patching the SSE helpers
so no real backend has to run. The gateway's own logic — namespacing, cache
priming, prefix dispatch, error semantics — is exercised directly through
the lower-level ``Server.request_handlers`` map.

The end-to-end SSE round-trip (browser-equivalent client connects to
``/gateway/sse``, calls a tool, gets a response from a real backend) is the
job of the integration suite, not this file.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from mcp import types

from hegemonikon import gateway as gw

# ── backends_from_env ───────────────────────────────────────────────────────


def test_backends_from_env_skips_unset_urls() -> None:
    env = {
        "NOESIS_LOGOS_URL": "http://logos:8000",
        "NOESIS_LOGOS_SECRET": "logos-secret",
        # mneme intentionally unset
        "NOESIS_PRAXIS_URL": "http://praxis:8000",
        # praxis secret intentionally unset
    }
    backends = gw.backends_from_env(env=env)
    assert [b.name for b in backends] == ["logos", "praxis"]
    logos = backends[0]
    assert logos.url == "http://logos:8000"
    assert logos.secret == "logos-secret"
    praxis = backends[1]
    assert praxis.url == "http://praxis:8000"
    assert praxis.secret == ""  # unset → empty, dev mode


def test_backends_from_env_empty() -> None:
    assert gw.backends_from_env(env={}) == []


def test_backends_from_env_honours_explicit_names() -> None:
    env = {
        "NOESIS_LOGOS_URL": "http://logos:8000",
        "NOESIS_MNEME_URL": "http://mneme:8000",
    }
    backends = gw.backends_from_env(names=("logos",), env=env)
    assert [b.name for b in backends] == ["logos"]


# ── list_tools handler: namespacing + cache + skip-failed-backends ──────────


def _tool(name: str) -> types.Tool:
    return types.Tool(
        name=name,
        description=f"desc for {name}",
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    )


def _backends(*names: str) -> list[gw.BackendConfig]:
    return [gw.BackendConfig(name=n, url=f"http://{n}:8000", secret="") for n in names]


async def _invoke_list_tools(server: Any) -> list[types.Tool]:
    handler = server.request_handlers[types.ListToolsRequest]
    req = types.ListToolsRequest(method="tools/list")
    result = await handler(req)
    return list(result.root.tools)


async def _invoke_call_tool(
    server: Any, name: str, arguments: dict[str, Any]
) -> Any:
    handler = server.request_handlers[types.CallToolRequest]
    req = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name=name, arguments=arguments),
    )
    return await handler(req)


@pytest.mark.asyncio
async def test_list_tools_namespaces_by_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_list(b: gw.BackendConfig) -> list[types.Tool]:
        # Return one tool per backend, named for the backend.
        return [_tool(f"tool_for_{b.name}")]

    monkeypatch.setattr(gw, "_list_remote_tools", fake_list)
    server = gw.build_gateway(_backends("logos", "mneme"))
    tools = await _invoke_list_tools(server)
    assert sorted(t.name for t in tools) == [
        "logos__tool_for_logos",
        "mneme__tool_for_mneme",
    ]


@pytest.mark.asyncio
async def test_list_tools_skips_failed_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_list(b: gw.BackendConfig) -> list[types.Tool]:
        # Real implementation returns [] on failure; mirror that.
        if b.name == "broken":
            return []
        return [_tool(f"tool_for_{b.name}")]

    monkeypatch.setattr(gw, "_list_remote_tools", fake_list)
    server = gw.build_gateway(_backends("logos", "broken", "mneme"))
    tools = await _invoke_list_tools(server)
    names = sorted(t.name for t in tools)
    assert names == ["logos__tool_for_logos", "mneme__tool_for_mneme"]


@pytest.mark.asyncio
async def test_list_tools_caches_after_first_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def fake_list(b: gw.BackendConfig) -> list[types.Tool]:
        nonlocal calls
        calls += 1
        return [_tool(f"tool_for_{b.name}")]

    monkeypatch.setattr(gw, "_list_remote_tools", fake_list)
    server = gw.build_gateway(_backends("logos", "mneme"))
    await _invoke_list_tools(server)
    await _invoke_list_tools(server)
    await _invoke_list_tools(server)
    # Two backends, primed once → exactly two upstream calls.
    assert calls == 2


# ── call_tool handler: dispatch by prefix ───────────────────────────────────


@pytest.mark.asyncio
async def test_call_tool_dispatches_to_correct_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_list(b: gw.BackendConfig) -> list[types.Tool]:
        return [_tool("do_thing")]

    seen: list[tuple[str, str, dict[str, Any]]] = []

    async def fake_call(
        b: gw.BackendConfig, tool_name: str, arguments: dict[str, Any]
    ) -> list[types.ContentBlock]:
        seen.append((b.name, tool_name, arguments))
        return [types.TextContent(type="text", text=f"{b.name} done")]

    monkeypatch.setattr(gw, "_list_remote_tools", fake_list)
    monkeypatch.setattr(gw, "_call_remote_tool", fake_call)
    server = gw.build_gateway(_backends("logos", "mneme"))

    # Prime cache (so call_tool's input validator can find the schema).
    await _invoke_list_tools(server)

    # Dispatch through mneme.
    result = await _invoke_call_tool(server, "mneme__do_thing", {"x": 1})
    assert seen == [("mneme", "do_thing", {"x": 1})]
    # Result content carries the backend's payload.
    assert "mneme done" in str(result)


@pytest.mark.asyncio
async def test_call_tool_unknown_backend_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_list(b: gw.BackendConfig) -> list[types.Tool]:
        return [_tool("do_thing")]

    monkeypatch.setattr(gw, "_list_remote_tools", fake_list)
    server = gw.build_gateway(_backends("logos"))
    await _invoke_list_tools(server)
    result = await _invoke_call_tool(server, "ghost__do_thing", {})
    # Server.call_tool wraps exceptions into an isError result.
    assert result.root.isError is True


@pytest.mark.asyncio
async def test_call_tool_missing_namespace_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_list(b: gw.BackendConfig) -> list[types.Tool]:
        return [_tool("do_thing")]

    monkeypatch.setattr(gw, "_list_remote_tools", fake_list)
    server = gw.build_gateway(_backends("logos"))
    await _invoke_list_tools(server)
    # No prefix at all — bare tool name.
    result = await _invoke_call_tool(server, "do_thing", {})
    assert result.root.isError is True


# ── routes wiring ───────────────────────────────────────────────────────────


def test_gateway_routes_uses_prefix() -> None:
    server = gw.build_gateway([])
    routes = gw.gateway_routes(server, mount_prefix="/g")
    paths = [getattr(r, "path", None) for r in routes]
    assert "/g/sse" in paths
    assert "/g/messages" in paths


def test_gateway_routes_default_prefix() -> None:
    server = gw.build_gateway([])
    routes = gw.gateway_routes(server)
    paths = [getattr(r, "path", None) for r in routes]
    assert "/gateway/sse" in paths
    assert "/gateway/messages" in paths


# ── transport security from env ─────────────────────────────────────────────


def test_transport_security_from_env_disables_protection_when_unset() -> None:
    s = gw.transport_security_from_env(env={})
    assert s.enable_dns_rebinding_protection is False
    # Localhost hosts always present so dev workflows still work.
    assert "127.0.0.1:*" in s.allowed_hosts


def test_transport_security_from_env_enables_when_hosts_listed() -> None:
    env = {"HEGEMONIKON_ALLOWED_HOSTS": "noesis-hegemonikon.up.railway.app"}
    s = gw.transport_security_from_env(env=env)
    assert s.enable_dns_rebinding_protection is True
    assert "noesis-hegemonikon.up.railway.app" in s.allowed_hosts
    assert "https://noesis-hegemonikon.up.railway.app" in s.allowed_origins


def test_transport_security_from_env_strips_and_splits_on_commas() -> None:
    env = {"HEGEMONIKON_ALLOWED_HOSTS": " host-a.example.com , host-b.example.com ,"}
    s = gw.transport_security_from_env(env=env)
    assert "host-a.example.com" in s.allowed_hosts
    assert "host-b.example.com" in s.allowed_hosts
    # Empty trailing comma element should be dropped.
    assert "" not in s.allowed_hosts


def test_sse_route_endpoint_takes_request_not_raw_asgi() -> None:
    """Regression for: TypeError: handle_sse() missing 2 required positional
    arguments: 'receive' and 'send'.

    Starlette's ``Route`` wraps endpoint callables as ``func(request)`` via
    ``request_response``. If the endpoint is raw ASGI (``(scope, receive,
    send)``), the wrapping breaks at request time with a TypeError. The
    gateway route must use a thin Request → ASGI adapter so Route's wrapper
    sees a single-arg endpoint."""
    import inspect

    from starlette.routing import Route

    server = gw.build_gateway([])
    routes = gw.gateway_routes(server)
    sse_route = next(r for r in routes if isinstance(r, Route))
    sig = inspect.signature(sse_route.endpoint)
    assert len(sig.parameters) == 1, (
        f"Route endpoint must take exactly 1 arg (Request), got "
        f"{list(sig.parameters)}. Raw-ASGI signature here causes a 500 at "
        f"request time, not at boot — see PR-#102 follow-up."
    )


# ── _list_remote_tools error path (no real SSE server) ─────────────────────


@pytest.mark.asyncio
async def test_list_remote_tools_returns_empty_on_unreachable_backend() -> None:
    # 127.0.0.1:1 is reliably refused on Linux/macOS without needing a server.
    b = gw.BackendConfig(name="ghost", url="http://127.0.0.1:1", secret="")
    result = await asyncio.wait_for(gw._list_remote_tools(b), timeout=10.0)
    assert result == []
