"""Unit tests for the Logos sidecar client.

Pins the contract:

* ``LogosClient.from_env`` returns ``None`` when ``LOGOS_URL`` is
  unset — the explicit "Logos isn't here, fall back" signal so
  callers can short-circuit without an exception.
* ``certify_claim`` parses the production response shape (CallToolResult
  with TextContent → JSON dict → ``certificate_json`` → ``ProofCertificate``)
  and round-trips a real Logos-shaped payload.
* Every failure mode (network error, missing field, bad JSON, schema
  mismatch, empty argument) returns ``None`` and stamps ``last_error``.
  No exception ever escapes — the rule is that a Logos outage must
  never break the caller's ``store_memory`` path.
* The session factory is injectable so this entire suite runs
  without a network: a hand-rolled fake mirrors the SDK's
  call-tool surface.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Coroutine, Mapping
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from noesis_clients.logos import LogosClient, _extract_certificate_json

T = TypeVar("T")


def _run(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine to completion in a fresh event loop.

    The Mneme test deps don't include pytest-asyncio (and we don't
    want to add it just for one client), so async behaviour is
    exercised through a trivial sync wrapper that creates and
    disposes a per-test event loop. ``asyncio.run`` does the right
    thing here because LogosClient is stateless across calls.
    """
    return asyncio.run(coro)


# ── fakes ────────────────────────────────────────────────────────────────────


class _FakeContent:
    """Stand-in for ``mcp.types.TextContent`` — only the ``text``
    attribute is exercised by the client."""

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeCallToolResult:
    """Mirror MCP's CallToolResult shape: a ``content`` list whose
    first item carries the response text."""

    def __init__(self, text: str) -> None:
        self.content = [_FakeContent(text)]


class _FakeSession:
    """Records the last ``call_tool`` invocation and returns a
    pre-canned response. Mimics ``mcp.ClientSession`` closely enough
    for the LogosClient to drive it through one call."""

    def __init__(self, response: Any) -> None:
        self.response = response
        self.last_tool_name: str | None = None
        self.last_arguments: Mapping[str, Any] | None = None
        self.initialized = False

    async def initialize(self) -> None:
        self.initialized = True

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Any:
        self.last_tool_name = name
        self.last_arguments = arguments
        return self.response


def _factory_returning(session: _FakeSession) -> Any:
    """Build a session_factory that hands the same fake out every time."""

    @asynccontextmanager
    async def _f(url: str, secret: str) -> AsyncIterator[_FakeSession]:
        yield session

    return _f


def _factory_raising(exc: BaseException) -> Any:
    """Session factory whose first ``__aenter__`` raises ``exc``,
    simulating handshake / SSE failure."""

    @asynccontextmanager
    async def _f(url: str, secret: str) -> AsyncIterator[_FakeSession]:
        raise exc
        # Unreachable yield; keeps the function a generator so
        # asynccontextmanager works.
        yield _FakeSession(None)

    return _f


# ── canonical Logos response ─────────────────────────────────────────────────


_GOOD_CERT = {
    "schema_version": "1.0",
    "claim_type": "propositional",
    "claim": "rain implies wet",
    "method": "z3_propositional",
    "verified": True,
    "timestamp": "2026-04-22T00:00:00Z",
    "verification_artifact": {"smt": "..."},
}


def _logos_response_text(cert: dict[str, Any] | None = None) -> str:
    """Produce the exact JSON shape Logos returns from certify_claim:
    a top-level dict with ``certificate_json`` containing the
    serialised cert string."""
    cert = cert if cert is not None else _GOOD_CERT
    return json.dumps(
        {
            "status": "certified",
            "verified": cert["verified"],
            "method": cert["method"],
            "certificate_json": json.dumps(cert),
            "certificate_id": "abc123",
        }
    )


# ── from_env ─────────────────────────────────────────────────────────────────


def test_from_env_returns_none_when_url_unset() -> None:
    """The "Logos not configured" signal is a None return, not an
    exception — callers must be able to short-circuit cleanly."""
    assert LogosClient.from_env(env={}) is None
    assert LogosClient.from_env(env={"LOGOS_URL": ""}) is None
    assert LogosClient.from_env(env={"LOGOS_URL": "   "}) is None


def test_from_env_strips_trailing_slash_and_keeps_secret() -> None:
    client = LogosClient.from_env(
        env={"LOGOS_URL": "https://logos.example/", "LOGOS_SECRET": "tok"}
    )
    assert client is not None
    assert client._url == "https://logos.example"
    assert client._secret == "tok"


# ── certify_claim happy path ─────────────────────────────────────────────────


def test_certify_claim_parses_production_response_shape() -> None:
    """Drive the client end-to-end against a fake session that
    returns the exact CallToolResult shape Logos emits via FastMCP.
    """
    session = _FakeSession(_FakeCallToolResult(_logos_response_text()))
    client = LogosClient(
        "https://logos.example",
        "tok",
        session_factory=_factory_returning(session),
    )
    cert = _run(client.certify_claim("rain implies wet"))
    assert cert is not None
    assert cert.verified is True
    assert cert.method == "z3_propositional"
    assert cert.claim == "rain implies wet"
    assert client.last_error is None
    # Tool name + payload must match Logos's MCP signature exactly,
    # otherwise the call would fail at the server.
    assert session.last_tool_name == "certify_claim"
    assert session.last_arguments == {"argument": "rain implies wet"}


def test_certify_claim_accepts_dict_response_for_test_ergonomics() -> None:
    """Tests don't always want to construct CallToolResult/TextContent;
    the client also accepts a bare dict that mimics Logos's payload."""
    session = _FakeSession(
        {
            "status": "certified",
            "verified": True,
            "method": "z3_propositional",
            "certificate_json": json.dumps(_GOOD_CERT),
            "certificate_id": "abc",
        }
    )
    client = LogosClient(
        "https://logos.example",
        session_factory=_factory_returning(session),
    )
    cert = _run(client.certify_claim("p implies q"))
    assert cert is not None
    assert cert.verified is True


def test_certify_claim_accepts_bare_json_string_response() -> None:
    """Same ergonomic shortcut for tests / debugging: a JSON-string
    response decodes to the same dict. Keeps the parser uniform
    across the three legit shapes."""
    session = _FakeSession(_logos_response_text())
    client = LogosClient(
        "https://logos.example",
        session_factory=_factory_returning(session),
    )
    cert = _run(client.certify_claim("p implies q"))
    assert cert is not None


# ── certify_claim failure modes (must never raise) ───────────────────────────


def test_certify_claim_returns_none_when_session_factory_raises() -> None:
    """Network outage → None + last_error populated. The caller's
    store_memory must keep working; we never propagate the exception."""

    class _Fake502:
        status_code = 502

    class _HTTPStatusError(Exception):
        def __init__(self) -> None:
            super().__init__("502 Bad Gateway")
            self.response = _Fake502()

    client = LogosClient(
        "https://logos.example",
        session_factory=_factory_raising(_HTTPStatusError()),
    )
    cert = _run(client.certify_claim("p implies q"))
    assert cert is None
    assert client.last_error is not None
    assert "HTTPStatusError" in client.last_error


def test_certify_claim_returns_none_on_missing_certificate_json() -> None:
    """Logos response without ``certificate_json`` (e.g. a bare error
    payload) → None + last_error mentioning the bad shape."""
    session = _FakeSession({"status": "error", "message": "bad input"})
    client = LogosClient(
        "https://logos.example",
        session_factory=_factory_returning(session),
    )
    assert _run(client.certify_claim("p implies q")) is None
    assert "certificate_json" in (client.last_error or "")


def test_certify_claim_returns_none_on_invalid_json_in_certificate() -> None:
    """``certificate_json`` present but not parseable → None.
    Defends against schema drift between Logos and Mneme's pydantic
    side without raising into the caller."""
    session = _FakeSession({"certificate_json": "{not valid json"})
    client = LogosClient(
        "https://logos.example",
        session_factory=_factory_returning(session),
    )
    assert _run(client.certify_claim("p implies q")) is None
    assert "valid JSON" in (client.last_error or "")


def test_certify_claim_returns_none_on_schema_mismatch() -> None:
    """Cert JSON parses but doesn't match ProofCertificate schema —
    e.g. Logos started returning a new claim_type Mneme doesn't know.
    None + last_error so the failure is visible without exception."""
    bad = {**_GOOD_CERT}
    del bad["claim_type"]  # required field
    session = _FakeSession({"certificate_json": json.dumps(bad)})
    client = LogosClient(
        "https://logos.example",
        session_factory=_factory_returning(session),
    )
    assert _run(client.certify_claim("p implies q")) is None
    assert "schema validation" in (client.last_error or "")


def test_certify_claim_rejects_empty_argument_locally() -> None:
    """No round trip should happen for a blank argument — Logos would
    just bounce it. Pin this so we don't burn budget on no-ops.
    """
    session = _FakeSession(_FakeCallToolResult(_logos_response_text()))
    client = LogosClient(
        "https://logos.example",
        session_factory=_factory_returning(session),
    )
    assert _run(client.certify_claim("   ")) is None
    # Crucial: session was never touched.
    assert session.last_tool_name is None
    assert "empty" in (client.last_error or "").lower()


def test_last_error_clears_on_successful_call_after_failure() -> None:
    """Caller chaining multiple calls should only see ``last_error``
    from the most recent call — otherwise a stale error after a
    later success would mislead any logging that reads ``last_error``.
    """
    session = _FakeSession(_FakeCallToolResult(_logos_response_text()))
    client = LogosClient(
        "https://logos.example",
        session_factory=_factory_returning(session),
    )
    # Force a failure first.
    _run(client.certify_claim(""))
    assert client.last_error is not None
    # Then a success.
    cert = _run(client.certify_claim("p implies q"))
    assert cert is not None
    assert client.last_error is None


# ── _extract_certificate_json edge cases ─────────────────────────────────────


def test_extract_handles_none_input() -> None:
    assert _extract_certificate_json(None) is None


def test_extract_handles_empty_content_list() -> None:
    """MCP responses with empty content arrays — possible from a
    misbehaving server — must not raise."""

    class _Empty:
        content: list[Any] = []

    assert _extract_certificate_json(_Empty()) is None


def test_extract_returns_none_when_certificate_json_is_not_a_string() -> None:
    """Defends against Logos accidentally returning a dict here
    instead of the JSON-encoded string we expect."""
    assert _extract_certificate_json({"certificate_json": {"oops": 1}}) is None
