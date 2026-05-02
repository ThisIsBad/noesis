"""Logos sidecar client — async MCP wrapper around Logos's read-only verification tools.

Multiple Noesis services (Mneme, Praxis, and later Telos / Episteme)
need to call Logos for verification. Routing every such call through
Claude as orchestrator costs 4× round trips per request — the
Logos-as-sidecar exception in the ROADMAP's ``Kommunikations-Pattern``
lets read-only, idempotent calls bypass Claude. Each caller owns its
own integration; this client is the shared transport they plug into.

Callers that use this client:

* **Mneme** — ``certify_claim(memory.content)`` on store / on demand
  via the ``certify_memory`` MCP tool, auto-graduating beliefs with
  a ``ProofCertificate``.
* **Praxis** — (planned) ``certify_claim`` over a plan's goal to
  attach a certificate before ``commit_step``.
* **Telos** — (planned) same path for goal-contract verification.

Failure mode: every public coroutine returns ``None`` instead of
raising on any network / SSE / schema problem. Logos is best-effort
from every caller's perspective — losing a verification chance must
not prevent the caller's primary operation from succeeding. The
``last_error`` attribute carries the exception string for callers
that want to log or surface it.

Transport notes: the default ``session_factory`` opens an MCP/SSE
session against ``<url>/sse``. ``url`` is whatever the caller passes
— typically the service's own env envelope (``LOGOS_URL``). For
Railway deployments the internal hostname ``logos.railway.internal``
works the same way and avoids the edge round-trip; the client is
agnostic to which one's configured.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator, Mapping
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from typing import Any, Callable, Protocol

from noesis_schemas import ProofCertificate

log = logging.getLogger("mneme.logos_client")


_RETRY_STATUS = {502, 503, 504}
"""Railway edge returns these on cold-start; the SDK surfaces them
through the SSE handshake. Worth a single retry; not worth retrying
inside a tool call (those are usually real errors)."""


class _Session(Protocol):
    """Subset of ``mcp.ClientSession`` we depend on. Lets tests pass
    a hand-rolled fake without standing up a real SSE connection."""

    async def initialize(self) -> Any: ...

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Any: ...


SessionFactory = Callable[[str, str], AbstractAsyncContextManager["_Session"]]
"""``(url, secret) -> async context manager yielding a Session``.
Defaults to a real MCP+SSE session; tests inject a no-network fake."""


@asynccontextmanager
async def _real_mcp_session(url: str, secret: str) -> AsyncIterator[_Session]:
    """Real MCP-over-SSE session against ``<url>/sse``.

    One retry on the handshake to ride out Railway cold-starts;
    no retry inside the yielded session (those are application-level
    failures the caller should surface, not silently retry).
    """
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    headers = {"Authorization": f"Bearer {secret}"} if secret else None
    backoff = 1.0
    async with AsyncExitStack() as outer:
        session: _Session | None = None
        for attempt in range(2):
            inner = AsyncExitStack()
            try:
                read, write = await inner.enter_async_context(
                    sse_client(f"{url}/sse", headers=headers)
                )
                client_session = await inner.enter_async_context(
                    ClientSession(read, write)
                )
                await client_session.initialize()
                session = client_session
            except BaseException as exc:
                await inner.aclose()
                if attempt == 0 and _is_retryable(exc):
                    await asyncio.sleep(backoff)
                    continue
                raise
            outer.push_async_callback(inner.aclose)
            break
        # Unreachable: the loop either yields a session or re-raises.
        assert session is not None
        yield session


def _is_retryable(exc: BaseException) -> bool:
    """Mirror the eval-suite's retry classifier without importing httpx
    here — services/mneme already pulls in httpx, but the classifier
    is tiny and avoiding the import keeps test mocking simpler."""
    name = type(exc).__name__
    if name in {
        "ConnectError",
        "ConnectTimeout",
        "ReadError",
        "ReadTimeout",
        "RemoteProtocolError",
    }:
        return True
    if name == "HTTPStatusError":
        # httpx.HTTPStatusError exposes ``response.status_code``; only
        # 5xx cold-start codes are worth a retry.
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        return status in _RETRY_STATUS
    if isinstance(exc, BaseExceptionGroup):
        return any(_is_retryable(e) for e in exc.exceptions)
    return False


class LogosClient:
    """Async sidecar client for Logos's read-only verification tools.

    Stateless — no persistent session is held; each public coroutine
    opens a fresh MCP session, runs one tool call, and tears down.
    Cheap relative to a verification call (Z3 is the cost driver) and
    avoids the bookkeeping of a long-lived connection.

    ``last_error`` is set whenever a public coroutine returns ``None``
    so callers can log or surface the failure without changing the
    return contract.
    """

    def __init__(
        self,
        url: str,
        secret: str = "",
        *,
        session_factory: SessionFactory | None = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._secret = secret
        self._session_factory: SessionFactory = session_factory or _real_mcp_session
        self.last_error: str | None = None

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        session_factory: SessionFactory | None = None,
    ) -> "LogosClient | None":
        """Build a client from the deployed-service env envelope.

        Reads ``LOGOS_URL`` (required; returns ``None`` if absent) and
        ``LOGOS_SECRET`` (optional). The ``None`` return is the
        explicit "Logos isn't configured here, fall back to the
        non-graduation path" signal — callers must check.
        """
        env = env if env is not None else os.environ
        url = env.get("LOGOS_URL", "").strip()
        if not url:
            return None
        secret = env.get("LOGOS_SECRET", "")
        return cls(url, secret, session_factory=session_factory)

    async def certify_claim(self, argument: str) -> ProofCertificate | None:
        """Ask Logos to verify ``argument`` and return its certificate.

        Returns ``None`` if Logos was unreachable, returned an
        un-parseable response, refuted the claim, or any other
        failure mode. Sets ``last_error`` to the human-readable
        reason so callers can log without re-raising.

        The claim is taken verbatim — Logos itself parses the
        argument into propositional / FOL form. Mneme passes the
        memory ``content`` directly; future PRs may pre-format
        memories that are too freeform to parse.
        """
        if not argument.strip():
            self.last_error = "empty argument — refusing to call Logos"
            return None

        try:
            async with self._session_factory(self._url, self._secret) as session:
                raw = await session.call_tool("certify_claim", {"argument": argument})
        except BaseException as exc:
            # Catch BaseException to include CancelledError / TaskGroup
            # exceptions from the SSE plumbing — caller still gets None.
            self.last_error = f"{type(exc).__name__}: {exc}"
            log.warning("Logos certify_claim failed: %s", self.last_error)
            return None

        cert_json = _extract_certificate_json(raw)
        if cert_json is None:
            self.last_error = f"no certificate_json in Logos response: {raw!r}"
            log.warning(self.last_error)
            return None

        try:
            data = json.loads(cert_json)
        except json.JSONDecodeError as exc:
            self.last_error = f"certificate_json not valid JSON: {exc}"
            log.warning(self.last_error)
            return None

        try:
            cert = ProofCertificate.model_validate(data)
        except Exception as exc:
            self.last_error = (
                f"certificate failed schema validation: {type(exc).__name__}: {exc}"
            )
            log.warning(self.last_error)
            return None

        # Reset on success so callers can chain calls and only ever
        # see last_error from the most recent failure.
        self.last_error = None
        return cert


def _extract_certificate_json(raw: Any) -> str | None:
    """Pull ``certificate_json`` out of whatever shape Logos returned.

    Logos's MCP wrapper returns a JSON-serialised dict as a string
    in the tool result's first text content block. The MCP SDK gives
    us back a ``CallToolResult``-like object with a ``content`` list.
    This helper handles three legit shapes:

    1. ``CallToolResult`` with ``content=[TextContent(text=...)]``
       — the production path.
    2. A bare dict (test fakes).
    3. A bare JSON string (also test fakes).
    """
    payload: Any
    if isinstance(raw, dict):
        payload = raw
    elif isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
    else:
        # Try the MCP SDK shape: raw.content is a list with a text item.
        content = getattr(raw, "content", None)
        if not content:
            return None
        text = getattr(content[0], "text", None)
        if not text:
            return None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    cert_json = payload.get("certificate_json")
    if not isinstance(cert_json, str):
        return None
    return cert_json


__all__ = ["LogosClient", "SessionFactory"]
