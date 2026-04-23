"""Contract tests for the shared ``noesis_clients.testing`` helpers.

These cover the fakes themselves so regressions in the stand-ins
fail fast — the services that rely on them can then trust the
contract.
"""

from __future__ import annotations

import asyncio

from noesis_clients.testing import (
    FakeLogosClient,
    refuted_certificate,
    verified_certificate,
)


def test_fake_logos_client_records_calls_and_returns_response() -> None:
    cert = verified_certificate()
    fake = FakeLogosClient(cert)

    got = asyncio.run(fake.certify_claim("the claim"))

    assert got is cert
    assert fake.calls == ["the claim"]
    assert fake.last_error is None


def test_fake_logos_client_none_response_simulates_unreachable() -> None:
    fake = FakeLogosClient(None, last_error="connection refused")

    got = asyncio.run(fake.certify_claim("anything"))

    assert got is None
    assert fake.last_error == "connection refused"


def test_fake_logos_client_records_every_call_in_order() -> None:
    fake = FakeLogosClient(verified_certificate())

    async def _three() -> None:
        await fake.certify_claim("first")
        await fake.certify_claim("second")
        await fake.certify_claim("third")

    asyncio.run(_three())
    assert fake.calls == ["first", "second", "third"]


def test_verified_certificate_defaults_produce_valid_cert() -> None:
    cert = verified_certificate()
    assert cert.verified is True
    assert cert.method == "z3_propositional"
    assert cert.claim_type == "propositional"


def test_refuted_certificate_has_verified_false() -> None:
    cert = refuted_certificate()
    assert cert.verified is False


def test_certificate_factories_accept_overrides() -> None:
    cert = verified_certificate(
        claim="custom claim",
        method="z3_fol",
        claim_type="fol",
        timestamp="2030-01-01T00:00:00+00:00",
    )
    assert cert.claim == "custom claim"
    assert cert.method == "z3_fol"
    assert cert.claim_type == "fol"
    assert cert.timestamp == "2030-01-01T00:00:00+00:00"
