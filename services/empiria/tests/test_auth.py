"""Wiring smoke test — Empiria uses the shared bearer-token gate.

Deep behaviour is covered in ``clients/tests/test_auth.py``. This file
pins that Empiria wires the shared helper correctly.
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

    return Starlette(
        routes=[
            Route("/spans", _ok),
            Route("/health", _health),
        ]
    )


def _build_app(env: dict[str, str], monkeypatch) -> Starlette:
    for name in ("EMPIRIA_SECRET", "EMPIRIA_SECRET_PREV"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    app = _downstream()
    app.add_middleware(bearer_middleware("EMPIRIA_SECRET"))
    return app


def test_health_bypasses_auth_even_when_secret_is_set(monkeypatch):
    app = _build_app({"EMPIRIA_SECRET": "test-secret"}, monkeypatch)
    client = TestClient(app)
    assert client.get("/health").status_code == 200


def test_no_secret_means_all_requests_pass(monkeypatch):
    app = _build_app({}, monkeypatch)
    client = TestClient(app)
    assert client.get("/spans").status_code == 200


def test_missing_authorization_header_rejected(monkeypatch):
    app = _build_app({"EMPIRIA_SECRET": "test-secret"}, monkeypatch)
    client = TestClient(app)
    resp = client.get("/spans")
    assert resp.status_code == 401
    assert resp.json() == {"error": "Unauthorized"}


def test_wrong_bearer_token_rejected(monkeypatch):
    app = _build_app({"EMPIRIA_SECRET": "test-secret"}, monkeypatch)
    client = TestClient(app)
    resp = client.get("/spans", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_correct_bearer_token_accepted(monkeypatch):
    app = _build_app({"EMPIRIA_SECRET": "test-secret"}, monkeypatch)
    client = TestClient(app)
    resp = client.get(
        "/spans", headers={"Authorization": "Bearer test-secret"}
    )
    assert resp.status_code == 200


def test_rotation_accepts_previous_token(monkeypatch):
    app = _build_app(
        {"EMPIRIA_SECRET": "new-token", "EMPIRIA_SECRET_PREV": "old-token"},
        monkeypatch,
    )
    client = TestClient(app)
    for token in ("new-token", "old-token"):
        resp = client.get(
            "/spans", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200, token


def test_server_module_imports_the_shared_middleware() -> None:
    import empiria.mcp_server_http as server

    assert not hasattr(server, "_BearerAuth")
    assert not hasattr(server, "_SECRET")
    assert server.bearer_middleware is bearer_middleware
    assert BearerAuthMiddleware is not None
