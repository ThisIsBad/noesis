"""Contract tests for the pure-ASGI Bearer auth gate.

``_BearerAuth`` is a security boundary — a regression (e.g. letting an
unauthenticated request through, or 500'ing instead of 401'ing) would
ship to Railway without tripping any existing test. These tests pin the
four-branch contract:

1. ``/health`` always bypasses auth (uptime probes must work without a
   token).
2. When ``MNEME_SECRET`` is unset, all requests pass (local dev mode).
3. With a secret configured, missing/wrong ``Authorization`` → 401 JSON
   ``{"error": "Unauthorized"}``.
4. With a secret configured, a matching ``Bearer <secret>`` passes
   through to the wrapped app.
"""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

import mneme.mcp_server_http as server


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


def test_health_bypasses_auth_even_when_secret_is_set(monkeypatch):
    monkeypatch.setattr(server, "_SECRET", "test-secret")
    app = server._BearerAuth(_downstream())
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200


def test_no_secret_means_all_requests_pass(monkeypatch):
    monkeypatch.setattr(server, "_SECRET", "")
    app = server._BearerAuth(_downstream())
    client = TestClient(app)
    resp = client.get("/spans")
    assert resp.status_code == 200


def test_missing_authorization_header_rejected(monkeypatch):
    monkeypatch.setattr(server, "_SECRET", "test-secret")
    app = server._BearerAuth(_downstream())
    client = TestClient(app)
    resp = client.get("/spans")
    assert resp.status_code == 401
    assert resp.json() == {"error": "Unauthorized"}


def test_wrong_bearer_token_rejected(monkeypatch):
    monkeypatch.setattr(server, "_SECRET", "test-secret")
    app = server._BearerAuth(_downstream())
    client = TestClient(app)
    resp = client.get("/spans", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401
    assert resp.json() == {"error": "Unauthorized"}


def test_correct_bearer_token_accepted(monkeypatch):
    monkeypatch.setattr(server, "_SECRET", "test-secret")
    app = server._BearerAuth(_downstream())
    client = TestClient(app)
    resp = client.get("/spans", headers={"Authorization": "Bearer test-secret"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
