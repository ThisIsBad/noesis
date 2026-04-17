"""Tests for the certify_claim MCP handler."""

from __future__ import annotations

from logos import ProofCertificate, verify_certificate
from logos.mcp_tools import certify_claim


def test_certify_claim_returns_verified_certificate_for_valid_argument() -> None:
    result = certify_claim({"argument": "P -> Q, P |- Q"})

    assert result["status"] == "certified"
    assert result["verified"] is True


def test_certify_claim_returns_refuted_for_invalid_argument() -> None:
    result = certify_claim({"argument": "P -> Q, Q |- P"})

    assert result["status"] == "refuted"
    assert result["verified"] is False


def test_certify_claim_rejects_empty_argument() -> None:
    result = certify_claim({"argument": ""})

    assert result["error"] == "Invalid input"


def test_certify_claim_certificate_json_roundtrip_is_reverifiable() -> None:
    result = certify_claim({"argument": "P -> Q, P |- Q"})

    cert = ProofCertificate.from_json(str(result["certificate_json"]))

    assert verify_certificate(cert) is True


def test_certify_claim_certificate_id_is_stable_for_same_input() -> None:
    first = certify_claim({"argument": "P -> Q, P |- Q"})
    second = certify_claim({"argument": "P -> Q, P |- Q"})

    assert first["certificate_id"] == second["certificate_id"]
