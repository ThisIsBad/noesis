from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

from theoria.server import make_server
from theoria.store import TraceStore


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def auth_server():
    store = TraceStore()
    port = _free_port()
    server, _ = make_server(host="127.0.0.1", port=port, store=store, secret="s3cret")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    try:
        yield base
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def _get(url: str, token: str | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url)
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _post(url: str, body: dict, token: str | None = None) -> tuple[int, bytes]:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_health_is_public_even_with_secret_set(auth_server) -> None:
    status, _ = _get(f"{auth_server}/health")
    assert status == 200


def test_static_index_is_public(auth_server) -> None:
    status, body = _get(f"{auth_server}/")
    assert status == 200
    assert b"Theoria" in body


def test_api_requires_bearer_token(auth_server) -> None:
    status, body = _get(f"{auth_server}/api/traces")
    assert status == 401
    payload = json.loads(body)
    assert payload["error"] == "unauthorized"


def test_api_wrong_token_rejected(auth_server) -> None:
    status, _ = _get(f"{auth_server}/api/traces", token="wrong")
    assert status == 401


def test_api_accepts_correct_token(auth_server) -> None:
    status, body = _get(f"{auth_server}/api/traces", token="s3cret")
    assert status == 200
    assert b"traces" in body


def test_post_requires_token(auth_server) -> None:
    trace = {
        "id": "t-auth", "title": "t", "question": "?",
        "source": "test", "kind": "custom", "root": "q",
        "steps": [{"id": "q", "kind": "question", "label": "Q", "status": "info"}],
    }
    status, _ = _post(f"{auth_server}/api/traces", trace)
    assert status == 401
    status, _ = _post(f"{auth_server}/api/traces", trace, token="s3cret")
    assert status == 201


def test_missing_authorization_returns_401_header(auth_server) -> None:
    req = urllib.request.Request(f"{auth_server}/api/traces")
    try:
        urllib.request.urlopen(req)
        assert False, "should have raised HTTPError"
    except urllib.error.HTTPError as exc:
        assert exc.code == 401
        assert exc.headers.get("WWW-Authenticate", "").startswith("Bearer")


def test_server_with_no_secret_permits_everything(monkeypatch) -> None:
    monkeypatch.delenv("THEORIA_SECRET", raising=False)
    monkeypatch.delenv("THEORIA_SECRET_PREV", raising=False)
    store = TraceStore()
    port = _free_port()
    server, _ = make_server(host="127.0.0.1", port=port, store=store, secret=None)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)
    try:
        status, _ = _get(f"http://127.0.0.1:{port}/api/traces")
        assert status == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def test_rotation_accepts_both_active_and_previous_token(monkeypatch) -> None:
    """During rotation THEORIA_SECRET + THEORIA_SECRET_PREV both pass.

    Mirrors the rotation contract that
    ``noesis_clients.auth.bearer_middleware`` provides for the ASGI
    services. Theoria stays stdlib-only so it can't share the middleware
    code itself, but the wire-level behaviour must match so an operator
    can rotate Theoria the same way as any other service.
    """
    monkeypatch.delenv("THEORIA_SECRET", raising=False)
    monkeypatch.delenv("THEORIA_SECRET_PREV", raising=False)
    store = TraceStore()
    port = _free_port()
    server, _ = make_server(
        host="127.0.0.1",
        port=port,
        store=store,
        secret="new-token",
        previous_secret="old-token",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    try:
        for token in ("new-token", "old-token"):
            status, _ = _get(f"{base}/api/traces", token=token)
            assert status == 200, token
        # An unrelated token still fails.
        status, _ = _get(f"{base}/api/traces", token="random")
        assert status == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def test_make_server_reads_previous_secret_from_env(monkeypatch) -> None:
    """``THEORIA_SECRET_PREV`` env var is honoured when no kwarg passed."""
    monkeypatch.setenv("THEORIA_SECRET", "active")
    monkeypatch.setenv("THEORIA_SECRET_PREV", "rotated-out")
    store = TraceStore()
    port = _free_port()
    server, _ = make_server(host="127.0.0.1", port=port, store=store)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    try:
        for token in ("active", "rotated-out"):
            status, _ = _get(f"{base}/api/traces", token=token)
            assert status == 200, token
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
