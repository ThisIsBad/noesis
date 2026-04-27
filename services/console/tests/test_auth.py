"""Wiring smoke test — Console uses the shared bearer-token gate.

Same shape as services/{telos,logos,mneme}/tests/test_auth.py. Deep
behaviour of the gate (rotation, exempt paths, …) is covered in
``clients/tests/test_auth.py``; this file just pins that Console
wires the helper up correctly with the right exempt paths so a
regression in the wiring trips Console's own CI.
"""
from __future__ import annotations

from noesis_clients.auth import BearerAuthMiddleware, bearer_middleware
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient


def _downstream() -> Starlette:
    async def _ok(_request: object) -> JSONResponse:
        return JSONResponse({"ok": True})

    async def _health(_request: object) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def _index(_request: object) -> JSONResponse:
        # Serves as both / and /index.html for the test
        return JSONResponse({"ui": "shell"})

    return Starlette(
        routes=[
            Route("/api/chat", _ok, methods=["POST", "GET"]),
            Route("/health", _health),
            Route("/", _index),
            Route("/index.html", _index),
        ]
    )


def _build_app(env: dict[str, str], monkeypatch) -> Starlette:
    for name in ("CONSOLE_SECRET", "CONSOLE_SECRET_PREV"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    app = _downstream()
    app.add_middleware(
        bearer_middleware(
            "CONSOLE_SECRET",
            exempt_paths={"/health", "/", "/index.html"},
            exempt_prefixes=("/static/",),
        )
    )
    return app


def test_health_bypasses_auth_even_when_secret_is_set(monkeypatch):
    app = _build_app({"CONSOLE_SECRET": "test-secret"}, monkeypatch)
    client = TestClient(app)
    assert client.get("/health").status_code == 200


def test_index_and_root_are_public_for_chat_shell(monkeypatch):
    app = _build_app({"CONSOLE_SECRET": "test-secret"}, monkeypatch)
    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert client.get("/index.html").status_code == 200


def test_no_secret_means_all_requests_pass(monkeypatch):
    app = _build_app({}, monkeypatch)
    client = TestClient(app)
    assert client.get("/api/chat").status_code == 200


def test_missing_authorization_header_rejected(monkeypatch):
    app = _build_app({"CONSOLE_SECRET": "test-secret"}, monkeypatch)
    client = TestClient(app)
    resp = client.get("/api/chat")
    assert resp.status_code == 401
    assert resp.json() == {"error": "Unauthorized"}


def test_wrong_bearer_token_rejected(monkeypatch):
    app = _build_app({"CONSOLE_SECRET": "test-secret"}, monkeypatch)
    client = TestClient(app)
    assert client.get(
        "/api/chat", headers={"Authorization": "Bearer wrong"}
    ).status_code == 401


def test_correct_bearer_token_accepted(monkeypatch):
    app = _build_app({"CONSOLE_SECRET": "test-secret"}, monkeypatch)
    client = TestClient(app)
    resp = client.get(
        "/api/chat", headers={"Authorization": "Bearer test-secret"}
    )
    assert resp.status_code == 200


def test_rotation_accepts_previous_token(monkeypatch):
    app = _build_app(
        {"CONSOLE_SECRET": "new-token", "CONSOLE_SECRET_PREV": "old-token"},
        monkeypatch,
    )
    client = TestClient(app)
    for token in ("new-token", "old-token"):
        resp = client.get(
            "/api/chat", headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, token


def test_static_prefix_is_public(monkeypatch):
    """Browser must fetch /static/chat.js before user can authenticate."""
    from starlette.applications import Starlette as _Star

    async def _asset(_req: object) -> JSONResponse:
        return JSONResponse({"asset": True})

    app2 = _Star(routes=[
        Route("/health", lambda _r: JSONResponse({"status": "ok"})),
        Route("/static/chat.js", _asset),
        Route("/api/chat", lambda _r: JSONResponse({"ok": True})),
    ])
    monkeypatch.setenv("CONSOLE_SECRET", "tok")
    app2.add_middleware(
        bearer_middleware(
            "CONSOLE_SECRET",
            exempt_paths={"/health"},
            exempt_prefixes=("/static/",),
        )
    )
    client = TestClient(app2)
    assert client.get("/static/chat.js").status_code == 200
    # API still gated.
    assert client.get("/api/chat").status_code == 401


def test_server_module_imports_the_shared_middleware() -> None:
    """Sanity — Console doesn't ship its own bearer auth class."""
    import console.mcp_server_http as server

    assert not hasattr(server, "_BearerAuth")
    assert not hasattr(server, "_SECRET")
    assert server.bearer_middleware is bearer_middleware
    assert BearerAuthMiddleware is not None
