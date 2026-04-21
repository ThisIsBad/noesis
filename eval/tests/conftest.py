"""Shared fixtures for the Noesis integration suite.

Each deployed service is exposed by two env vars::

    NOESIS_<SERVICE>_URL     — public Railway origin, no trailing slash
    NOESIS_<SERVICE>_SECRET  — bearer token (optional; required if the
                               service was deployed with <SERVICE>_SECRET set)

Any test that needs a service gets a fixture (e.g. ``mneme_url``) which
skips the test when the URL is unset. Bearer secrets are supplied by the
matching ``_secret`` fixture (empty string if unset) and baked into the
``mcp_session`` / ``http`` helpers.

A local ``eval/.env.e2e`` file is auto-loaded if present. See
``eval/.env.e2e.example`` for the template.
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover — optional dep
    load_dotenv = None


_ENV_PATH = Path(__file__).resolve().parents[1] / ".env.e2e"
if load_dotenv is not None and _ENV_PATH.exists():
    load_dotenv(_ENV_PATH, override=False)


# Railway edge returns 502/503/504 while a service container is cold-starting
# (first request after an idle spin-down). The MCP SDK surfaces that as an
# httpx.HTTPStatusError from the SSE handshake — before any RPC runs — so a
# one-shot retry on the handshake is enough. Don't retry inside the yield:
# those failures are test logic, not cold-start.
#
# ``sse_client`` runs the handshake inside an anyio TaskGroup, so the real
# failure arrives wrapped in a BaseExceptionGroup. We walk the group tree
# to find a retryable leaf.
_RETRY_STATUS = {502, 503, 504}
_RETRY_EXCEPTIONS: tuple[type[BaseException], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadError,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)


def _is_retryable_leaf(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRY_STATUS
    return isinstance(exc, _RETRY_EXCEPTIONS)


def _is_retryable(exc: BaseException) -> bool:
    if _is_retryable_leaf(exc):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_is_retryable(e) for e in exc.exceptions)
    return False


@asynccontextmanager
async def _mcp_session(url: str, secret: str = "") -> AsyncIterator[Any]:
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    headers = {"Authorization": f"Bearer {secret}"} if secret else None
    backoff = 2.0
    async with AsyncExitStack() as outer:
        session: Any = None
        for attempt in range(3):
            inner = AsyncExitStack()
            try:
                read, write = await inner.enter_async_context(
                    sse_client(f"{url}/sse", headers=headers)
                )
                session = await inner.enter_async_context(ClientSession(read, write))
                await session.initialize()
            except BaseException as exc:
                await inner.aclose()
                if attempt < 2 and _is_retryable(exc):
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                raise
            outer.push_async_callback(inner.aclose)
            break
        yield session


SERVICES = (
    "mneme", "telos", "praxis", "logos",
    "episteme", "empiria", "techne", "kosmos",
)


def _service_url(name: str) -> str:
    env_var = f"NOESIS_{name.upper()}_URL"
    url = os.getenv(env_var)
    if not url:
        pytest.skip(f"{env_var} not set — skipping integration test")
    return url.rstrip("/")


def _service_secret(name: str) -> str:
    return os.getenv(f"NOESIS_{name.upper()}_SECRET", "")


# ── URL fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def mneme_url() -> str:
    return _service_url("mneme")


@pytest.fixture
def telos_url() -> str:
    return _service_url("telos")


@pytest.fixture
def praxis_url() -> str:
    return _service_url("praxis")


@pytest.fixture
def logos_url() -> str:
    return _service_url("logos")


@pytest.fixture
def episteme_url() -> str:
    return _service_url("episteme")


@pytest.fixture
def empiria_url() -> str:
    return _service_url("empiria")


@pytest.fixture
def techne_url() -> str:
    return _service_url("techne")


@pytest.fixture
def kosmos_url() -> str:
    return _service_url("kosmos")


# ── Secret fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def mneme_secret() -> str:
    return _service_secret("mneme")


@pytest.fixture
def telos_secret() -> str:
    return _service_secret("telos")


@pytest.fixture
def praxis_secret() -> str:
    return _service_secret("praxis")


@pytest.fixture
def logos_secret() -> str:
    return _service_secret("logos")


@pytest.fixture
def episteme_secret() -> str:
    return _service_secret("episteme")


@pytest.fixture
def empiria_secret() -> str:
    return _service_secret("empiria")


@pytest.fixture
def techne_secret() -> str:
    return _service_secret("techne")


@pytest.fixture
def kosmos_secret() -> str:
    return _service_secret("kosmos")


# ── HTTP client ───────────────────────────────────────────────────────────────

@pytest.fixture
def http() -> httpx.Client:
    return httpx.Client(timeout=30.0)


# ── Cleanup helpers ───────────────────────────────────────────────────────────

@pytest.fixture
async def mneme_cleanup(mneme_url: str, mneme_secret: str) -> AsyncIterator[list[str]]:
    """Tests append memory_ids to the yielded list; teardown forgets them all.

    Keeps the deployed Mneme store from accumulating per-run e2e records. The
    fixture depends on ``mneme_url`` so it skips alongside the test when
    ``NOESIS_MNEME_URL`` is unset — no forget calls are attempted.
    """
    memory_ids: list[str] = []
    yield memory_ids
    if not memory_ids:
        return
    async with _mcp_session(mneme_url, mneme_secret) as session:
        for mid in memory_ids:
            try:
                await session.call_tool(
                    "forget_memory",
                    {"memory_id": mid, "reason": "e2e cleanup"},
                )
            except Exception:  # pragma: no cover — best-effort teardown
                pass
