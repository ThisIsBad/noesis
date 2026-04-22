"""Tests for the Mneme→Logos auto-graduation path.

Two layers covered:

* ``MnemeCore.attach_certificate`` (sync, in-process): updates SQLite
  + Chroma metadata in place, sets ``proven`` from the certificate's
  ``verified`` flag, surfaces through ``list_proven``, returns
  ``None`` if the memory is gone (so a forget-race is observable).
* ``certify_memory`` MCP tool (async, sidecar-driven): wires
  ``LogosClient.certify_claim`` into ``attach_certificate`` with a
  fully-classified return-status surface — never raises, always
  returns a valid JSON payload, even when Logos is unconfigured /
  unreachable / refutes the claim.

The MCP-tool tests monkey-patch ``mneme.mcp_server_http._logos_client``
to a fake ``LogosClient`` so no network is needed and we can drive
every status branch deterministically.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from typing import Any, TypeVar

import chromadb
import pytest
from noesis_schemas import MemoryType, ProofCertificate

from mneme.core import MnemeCore

T = TypeVar("T")


def _run(coro: Coroutine[Any, Any, T]) -> T:
    """Drive a coroutine through a fresh event loop.

    Mneme's dev deps don't carry pytest-asyncio / pytest-anyio; the
    MCP tool under test is a plain async function we can drive via
    ``asyncio.run`` from sync test bodies. Keeps the test-runner
    surface pluginless.
    """
    return asyncio.run(coro)


# ── core.attach_certificate ──────────────────────────────────────────────────


@pytest.fixture
def core(tmp_path: Any) -> MnemeCore:
    return MnemeCore(
        db_path=str(tmp_path / "test.db"),
        _chroma_client=chromadb.PersistentClient(
            path=str(tmp_path / "chroma")
        ),
    )


def _verified_cert(claim: str = "p implies q") -> ProofCertificate:
    return ProofCertificate(
        claim_type="propositional",
        claim=claim,
        method="z3_propositional",
        verified=True,
        timestamp="2026-04-22T00:00:00+00:00",
    )


def _refuted_cert(claim: str = "p implies q") -> ProofCertificate:
    return ProofCertificate(
        claim_type="propositional",
        claim=claim,
        method="z3_propositional",
        verified=False,
        timestamp="2026-04-22T00:00:00+00:00",
    )


def test_attach_certificate_marks_memory_proven(core: MnemeCore) -> None:
    """Pre-existing un-proven memory → attach a verified cert → memory
    is now ``proven`` and shows up in ``list_proven``."""
    mem = core.store("rain implies wet", MemoryType.SEMANTIC)
    assert mem.proven is False
    assert core.list_proven() == []

    updated = core.attach_certificate(mem.memory_id, _verified_cert())
    assert updated is not None
    assert updated.proven is True
    assert updated.certificate is not None
    assert updated.certificate.method == "z3_propositional"

    # Persisted: a fresh ``get`` reads the same updated state.
    fetched = core.get(mem.memory_id)
    assert fetched is not None
    assert fetched.proven is True
    proven = core.list_proven()
    assert len(proven) == 1
    assert proven[0].memory_id == mem.memory_id


def test_attach_refuted_certificate_keeps_proven_false(
    core: MnemeCore,
) -> None:
    """Logos can refute a claim — that still attaches a certificate but
    leaves ``proven=False``. ``list_proven`` must NOT pick it up."""
    mem = core.store("if p then not p", MemoryType.SEMANTIC)
    updated = core.attach_certificate(mem.memory_id, _refuted_cert())
    assert updated is not None
    assert updated.certificate is not None
    assert updated.certificate.verified is False
    assert updated.proven is False
    assert core.list_proven() == []


def test_attach_certificate_returns_none_for_unknown_memory(
    core: MnemeCore,
) -> None:
    """A forget happening between get() and attach() is observable as
    a ``None`` return — caller can decide to log + skip."""
    assert core.attach_certificate("does-not-exist", _verified_cert()) is None


def test_reattach_overwrites_previous_certificate(core: MnemeCore) -> None:
    """If Logos has gained a stronger method (e.g. FOL since last
    graduation), re-certifying must replace the old certificate
    rather than refusing or duplicating."""
    mem = core.store("rain implies wet", MemoryType.SEMANTIC)
    core.attach_certificate(mem.memory_id, _verified_cert())

    new_cert = ProofCertificate(
        claim_type="fol",
        claim="rain implies wet",
        method="z3_fol",
        verified=True,
        timestamp="2026-04-22T01:00:00+00:00",
    )
    updated = core.attach_certificate(mem.memory_id, new_cert)
    assert updated is not None
    assert updated.certificate is not None
    assert updated.certificate.method == "z3_fol"
    assert updated.certificate.claim_type == "fol"


def test_attach_certificate_is_visible_to_retrieve(core: MnemeCore) -> None:
    """Retrieval must see the post-attach state — Chroma metadata
    needs updating in lockstep with SQLite, otherwise ``min_confidence``
    + future filter-by-proven queries would diverge from
    ``list_proven``."""
    mem = core.store("the sky is blue", MemoryType.SEMANTIC, confidence=0.9)
    core.attach_certificate(mem.memory_id, _verified_cert())
    results = core.retrieve("sky colour")
    assert len(results) == 1
    assert results[0].memory_id == mem.memory_id
    assert results[0].proven is True


# ── certify_memory MCP tool ──────────────────────────────────────────────────


class _FakeLogos:
    """Drop-in replacement for the module-level LogosClient that
    returns whatever certificate (or None) the test asks for, and
    records the last argument seen so we can pin Mneme→Logos plumbing.
    """

    def __init__(self, cert: ProofCertificate | None = None,
                 last_error: str | None = None) -> None:
        self.cert = cert
        self.last_error = last_error
        self.last_argument: str | None = None

    async def certify_claim(self, argument: str) -> ProofCertificate | None:
        self.last_argument = argument
        return self.cert


@pytest.fixture
def patched_module(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> Any:
    """Import the MCP module and rewire its ``_core`` + ``_logos_client``
    to a per-test pair so each test starts on a clean store and a
    fresh fake Logos."""
    import mneme.mcp_server_http as mod

    fresh_core = MnemeCore(
        db_path=str(tmp_path / "core.db"),
        _chroma_client=chromadb.PersistentClient(
            path=str(tmp_path / "chroma")
        ),
    )
    monkeypatch.setattr(mod, "_core", fresh_core)
    return mod


def test_certify_memory_returns_certified_status_on_success(
    patched_module: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy path: existing memory + Logos returns a verified cert →
    JSON payload with status=certified, proven=true, method echoed."""
    mem = patched_module._core.store("rain implies wet", MemoryType.SEMANTIC)
    fake = _FakeLogos(cert=_verified_cert())
    monkeypatch.setattr(patched_module, "_logos_client", fake)

    raw = _run(patched_module._certify_memory_impl(
        memory_id=mem.memory_id,
        core=patched_module._core,
        logos_client=patched_module._logos_client,
    ))
    payload = json.loads(raw)
    assert payload["status"] == "certified"
    assert payload["memory_id"] == mem.memory_id
    assert payload["verified"] is True
    assert payload["proven"] is True
    assert payload["method"] == "z3_propositional"
    # Mneme passed the memory's content (not the ID or the goal) to Logos.
    assert fake.last_argument == "rain implies wet"
    # Side effect: the memory is now in list_proven.
    assert any(
        m.memory_id == mem.memory_id
        for m in patched_module._core.list_proven()
    )


def test_certify_memory_status_refuted_on_unverified_cert(
    patched_module: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Logos refutes the claim → status=refuted, proven=false. The
    cert is still attached (so future queries see "Logos was asked"),
    but ``proven`` is honest."""
    mem = patched_module._core.store("p and not p", MemoryType.SEMANTIC)
    monkeypatch.setattr(
        patched_module, "_logos_client", _FakeLogos(cert=_refuted_cert())
    )
    raw = _run(patched_module._certify_memory_impl(
        memory_id=mem.memory_id,
        core=patched_module._core,
        logos_client=patched_module._logos_client,
    ))
    payload = json.loads(raw)
    assert payload["status"] == "refuted"
    assert payload["verified"] is False
    assert payload["proven"] is False
    assert patched_module._core.list_proven() == []


def test_certify_memory_status_not_found_for_unknown_id(
    patched_module: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No memory with that ID → status=not_found, no Logos call.
    Bounds-checking happens before the network round-trip so we don't
    waste a Z3 invocation."""
    fake = _FakeLogos(cert=_verified_cert())
    monkeypatch.setattr(patched_module, "_logos_client", fake)
    raw = _run(patched_module._certify_memory_impl(
        memory_id="nope",
        core=patched_module._core,
        logos_client=patched_module._logos_client,
    ))
    payload = json.loads(raw)
    assert payload["status"] == "not_found"
    assert payload["memory_id"] == "nope"
    assert fake.last_argument is None


def test_certify_memory_status_unconfigured_when_logos_unset(
    patched_module: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``LOGOS_URL`` unset at boot → ``_logos_client`` is None →
    ``certify_memory`` reports status=logos_unconfigured. Distinct
    from logos_unreachable so the caller can tell "deployment
    issue" from "network blip"."""
    mem = patched_module._core.store("rain implies wet", MemoryType.SEMANTIC)
    monkeypatch.setattr(patched_module, "_logos_client", None)
    raw = _run(patched_module._certify_memory_impl(
        memory_id=mem.memory_id,
        core=patched_module._core,
        logos_client=patched_module._logos_client,
    ))
    payload = json.loads(raw)
    assert payload["status"] == "logos_unconfigured"


def test_certify_memory_status_unreachable_with_error(
    patched_module: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Logos returns None (network outage / bad response) →
    status=logos_unreachable + ``error`` field carrying
    ``LogosClient.last_error`` for diagnostics. Memory stays
    un-graduated; the run continues."""
    mem = patched_module._core.store("rain implies wet", MemoryType.SEMANTIC)
    fake = _FakeLogos(
        cert=None, last_error="ConnectError: connection refused"
    )
    monkeypatch.setattr(patched_module, "_logos_client", fake)
    raw = _run(patched_module._certify_memory_impl(
        memory_id=mem.memory_id,
        core=patched_module._core,
        logos_client=patched_module._logos_client,
    ))
    payload = json.loads(raw)
    assert payload["status"] == "logos_unreachable"
    assert payload["memory_id"] == mem.memory_id
    assert "ConnectError" in payload["error"]
    # Memory remains un-graduated.
    fetched = patched_module._core.get(mem.memory_id)
    assert fetched is not None
    assert fetched.proven is False


def test_certify_memory_unreachable_falls_back_to_unknown_error(
    patched_module: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``LogosClient.last_error`` is ``None`` if the client is fresh
    and never failed — then returned None for some other reason
    (e.g. empty argument). Tool surfaces a literal ``"unknown"``
    rather than ``None`` so JSON shape is consistent."""
    mem = patched_module._core.store("rain implies wet", MemoryType.SEMANTIC)
    fake = _FakeLogos(cert=None, last_error=None)
    monkeypatch.setattr(patched_module, "_logos_client", fake)
    raw = _run(patched_module._certify_memory_impl(
        memory_id=mem.memory_id,
        core=patched_module._core,
        logos_client=patched_module._logos_client,
    ))
    payload = json.loads(raw)
    assert payload["status"] == "logos_unreachable"
    assert payload["error"] == "unknown"
