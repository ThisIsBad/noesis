"""Contract tests for ``noesis_clients.auth.bearer_middleware``.

The helper is the single-source-of-truth for every Noesis service's
bearer-token gate, so regressions here break everyone. Tests drive
the middleware directly over the ASGI protocol so no Starlette app
has to be spun up.
"""

from __future__ import annotations

import asyncio
from typing import Any

from noesis_clients.auth import BearerAuthMiddleware


async def _stub_app(scope: dict, receive: Any, send: Any) -> None:
    """Minimal downstream app that records `called=True` via send()."""
    await send(
        {"type": "http.response.start", "status": 200, "headers": []}
    )
    await send({"type": "http.response.body", "body": b"ok"})


async def _drive(
    middleware: BearerAuthMiddleware, scope: dict
) -> tuple[int, dict[str, bytes]]:
    """Drive the middleware against a fake request, return (status, headers)."""
    status = {"code": 0}
    response_headers: dict[str, bytes] = {}

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg: dict) -> None:
        if msg["type"] == "http.response.start":
            status["code"] = msg["status"]
            for key, value in msg.get("headers") or []:
                response_headers[key if isinstance(key, bytes) else key.encode()] = (
                    value if isinstance(value, bytes) else value.encode()
                )

    await middleware(scope, receive, send)
    return status["code"], response_headers


def _http_scope(
    path: str = "/api/traces", headers: list[tuple[bytes, bytes]] | None = None
) -> dict:
    return {
        "type": "http",
        "path": path,
        "headers": headers or [],
    }


def test_no_secret_is_open_mode() -> None:
    mw = BearerAuthMiddleware(_stub_app, secret="")
    status, _ = asyncio.run(_drive(mw, _http_scope()))
    assert status == 200


def test_matching_token_passes() -> None:
    mw = BearerAuthMiddleware(_stub_app, secret="s3cret")
    scope = _http_scope(
        headers=[(b"authorization", b"Bearer s3cret")],
    )
    status, _ = asyncio.run(_drive(mw, scope))
    assert status == 200


def test_wrong_token_returns_401_with_www_authenticate() -> None:
    mw = BearerAuthMiddleware(_stub_app, secret="s3cret")
    scope = _http_scope(headers=[(b"authorization", b"Bearer nope")])
    status, headers = asyncio.run(_drive(mw, scope))
    assert status == 401
    assert headers.get(b"www-authenticate", b"").startswith(b"Bearer")


def test_missing_header_returns_401() -> None:
    mw = BearerAuthMiddleware(_stub_app, secret="s3cret")
    status, _ = asyncio.run(_drive(mw, _http_scope()))
    assert status == 401


def test_health_path_always_exempt() -> None:
    mw = BearerAuthMiddleware(_stub_app, secret="s3cret")
    status, _ = asyncio.run(_drive(mw, _http_scope(path="/health")))
    assert status == 200


def test_custom_exempt_paths() -> None:
    mw = BearerAuthMiddleware(
        _stub_app, secret="s3cret", exempt_paths={"/", "/health"},
    )
    status, _ = asyncio.run(_drive(mw, _http_scope(path="/")))
    assert status == 200


def test_exempt_prefixes_match() -> None:
    mw = BearerAuthMiddleware(
        _stub_app, secret="s3cret", exempt_prefixes=("/static/",),
    )
    status, _ = asyncio.run(_drive(mw, _http_scope(path="/static/app.js")))
    assert status == 200


def test_non_http_scope_passes_through() -> None:
    """WebSocket / lifespan scopes must not trigger auth checks."""
    lifespan_scope = {"type": "lifespan"}
    # Lifespan drives different messages; a simple call through is enough
    # to prove the middleware didn't intercept.
    async def receive() -> dict:
        return {"type": "lifespan.startup"}

    sent: list[dict] = []
    async def send(msg: dict) -> None:
        sent.append(msg)

    async def stub(scope: dict, r: Any, s: Any) -> None:
        await s({"type": "lifespan.startup.complete"})

    mw_passthrough = BearerAuthMiddleware(stub, secret="s3cret")
    asyncio.run(mw_passthrough(lifespan_scope, receive, send))
    assert sent == [{"type": "lifespan.startup.complete"}]


def test_bearer_middleware_factory_reads_env_at_construction(monkeypatch) -> None:
    from noesis_clients.auth import bearer_middleware

    monkeypatch.setenv("TEST_SVC_SECRET", "env-value")
    factory = bearer_middleware("TEST_SVC_SECRET")
    mw = factory(_stub_app)

    scope = _http_scope(headers=[(b"authorization", b"Bearer env-value")])
    status, _ = asyncio.run(_drive(mw, scope))
    assert status == 200

    # Wrong token rejected
    scope_wrong = _http_scope(headers=[(b"authorization", b"Bearer other")])
    status, _ = asyncio.run(_drive(mw, scope_wrong))
    assert status == 401


def test_bearer_middleware_factory_open_when_env_unset(monkeypatch) -> None:
    from noesis_clients.auth import bearer_middleware

    monkeypatch.delenv("UNSET_SECRET", raising=False)
    factory = bearer_middleware("UNSET_SECRET")
    mw = factory(_stub_app)

    status, _ = asyncio.run(_drive(mw, _http_scope()))
    assert status == 200


def test_bearer_middleware_factory_reads_env_at_construction_not_call(
    monkeypatch,
) -> None:
    """The secret is snapshotted when the factory is called, not later.

    This is explicit so an attacker who can write env in a running
    service process can't retroactively change the active token —
    the middleware has already captured it.
    """
    from noesis_clients.auth import bearer_middleware

    monkeypatch.setenv("FROZEN_SECRET", "initial")
    factory = bearer_middleware("FROZEN_SECRET")
    mw = factory(_stub_app)

    # Change env *after* factory construction.
    monkeypatch.setenv("FROZEN_SECRET", "different")

    scope = _http_scope(headers=[(b"authorization", b"Bearer initial")])
    status, _ = asyncio.run(_drive(mw, scope))
    assert status == 200    # original secret still honoured


# ── Rotation: <SVC>_SECRET + <SVC>_SECRET_PREV ────────────────────────────────

def test_rotation_both_tokens_accepted() -> None:
    """During the rotation window both active and previous tokens pass."""
    mw = BearerAuthMiddleware(
        _stub_app, secrets=("new-token", "old-token"),
    )
    for token in ("new-token", "old-token"):
        scope = _http_scope(headers=[(b"authorization", f"Bearer {token}".encode())])
        status, _ = asyncio.run(_drive(mw, scope))
        assert status == 200, f"{token!r} should be accepted during rotation"


def test_rotation_rejects_token_not_in_active_set() -> None:
    mw = BearerAuthMiddleware(
        _stub_app, secrets=("new-token", "old-token"),
    )
    scope = _http_scope(headers=[(b"authorization", b"Bearer stale-token")])
    status, _ = asyncio.run(_drive(mw, scope))
    assert status == 401


def test_rotation_empty_previous_is_ignored() -> None:
    """Unset <SVC>_SECRET_PREV must not collapse to accepting empty token."""
    mw = BearerAuthMiddleware(_stub_app, secrets=("active", ""))
    scope = _http_scope(headers=[(b"authorization", b"Bearer ")])
    status, _ = asyncio.run(_drive(mw, scope))
    assert status == 401
    # And a missing Authorization header is also rejected.
    status, _ = asyncio.run(_drive(mw, _http_scope()))
    assert status == 401


def test_bearer_middleware_reads_prev_env_var(monkeypatch) -> None:
    """Default prev env-var is ``<env_var>_PREV``."""
    from noesis_clients.auth import bearer_middleware

    monkeypatch.setenv("ROT_SECRET", "active")
    monkeypatch.setenv("ROT_SECRET_PREV", "previous")
    factory = bearer_middleware("ROT_SECRET")
    mw = factory(_stub_app)

    for token in ("active", "previous"):
        scope = _http_scope(headers=[(b"authorization", f"Bearer {token}".encode())])
        status, _ = asyncio.run(_drive(mw, scope))
        assert status == 200, f"{token} should work in rotation window"


def test_bearer_middleware_custom_prev_env_var(monkeypatch) -> None:
    """Caller can override the prev env-var name."""
    from noesis_clients.auth import bearer_middleware

    monkeypatch.setenv("CUR", "new")
    monkeypatch.setenv("OLD", "old")
    factory = bearer_middleware("CUR", prev_env_var="OLD")
    mw = factory(_stub_app)

    scope = _http_scope(headers=[(b"authorization", b"Bearer old")])
    status, _ = asyncio.run(_drive(mw, scope))
    assert status == 200


def test_bearer_middleware_no_prev_env_var_still_works(monkeypatch) -> None:
    """When only <SVC>_SECRET is set, behaviour matches Stage-1."""
    from noesis_clients.auth import bearer_middleware

    monkeypatch.setenv("STAGE1_SECRET", "only-token")
    monkeypatch.delenv("STAGE1_SECRET_PREV", raising=False)
    factory = bearer_middleware("STAGE1_SECRET")
    mw = factory(_stub_app)

    scope = _http_scope(headers=[(b"authorization", b"Bearer only-token")])
    status, _ = asyncio.run(_drive(mw, scope))
    assert status == 200


def test_duplicate_secrets_are_deduplicated() -> None:
    """Same string for both active and prev collapses to one."""
    mw = BearerAuthMiddleware(_stub_app, secrets=("same", "same"))
    assert mw.secrets == ("same",)
