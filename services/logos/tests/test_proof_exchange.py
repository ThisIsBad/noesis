"""Tests for proof exchange protocol (Issue #37)."""

from __future__ import annotations

import pytest

from logos import (
    ProofBundle,
    ProofCertificate,
    create_proof_bundle,
    certify,
    verify_proof_bundle,
)


def test_bundle_roundtrip_and_verification() -> None:
    cert_a = certify("P -> Q, P |- Q")
    cert_b = certify("P -> Q, Q |- P")

    bundle = create_proof_bundle(
        nodes={"n1": cert_a, "n2": cert_b},
        dependencies={"n2": ["n1"]},
        roots=["n2"],
    )

    restored = ProofBundle.from_json(bundle.to_json())
    result = verify_proof_bundle(restored)

    assert result.valid_bundle is True
    assert result.complete is True
    assert result.invalid_nodes == []
    assert result.invalid_roots == []
    assert result.diagnostics == []


def test_partial_bundle_is_reported_but_still_valid_if_nodes_verify() -> None:
    cert = certify("P -> Q, P |- Q")

    bundle = create_proof_bundle(
        nodes={"n2": cert},
        dependencies={"n2": ["n1"]},
        roots=["n2"],
    )

    result = verify_proof_bundle(bundle)
    assert result.valid_bundle is True
    assert result.complete is False
    assert result.missing_dependencies == ["n2->n1"]
    assert result.invalid_roots == []
    assert any(item["code"] == "missing_dependency" for item in result.diagnostics)


def test_tampered_certificate_is_flagged_invalid() -> None:
    cert = certify("P -> Q, P |- Q")
    tampered = cert.to_dict()
    tampered["verified"] = False

    bundle = ProofBundle.from_dict(
        {
            "schema_version": "1.0",
            "roots": ["n1"],
            "nodes": [
                {
                    "node_id": "n1",
                    "certificate": tampered,
                    "depends_on": [],
                }
            ],
        }
    )

    result = verify_proof_bundle(bundle)
    assert result.valid_bundle is False
    assert result.invalid_nodes == ["n1"]
    assert any(item["code"] == "certificate_mismatch" for item in result.diagnostics)


def test_invalid_roots_are_reported_as_incomplete_bundle() -> None:
    cert = certify("P |- P")
    bundle = create_proof_bundle(nodes={"n1": cert}, roots=["missing_root"])

    result = verify_proof_bundle(bundle)

    assert result.valid_bundle is True
    assert result.complete is False
    assert result.invalid_roots == ["missing_root"]
    assert any(item["code"] == "invalid_root" for item in result.diagnostics)


def test_certificate_errors_are_reported_with_structured_diagnostics() -> None:
    invalid_cert = ProofCertificate(
        schema_version="1.0",
        claim_type="unknown",
        claim="P |- P",
        method="none",
        verified=True,
        timestamp="2026-01-01T00:00:00+00:00",
        verification_artifact={},
    )
    bundle = create_proof_bundle(nodes={"n1": invalid_cert}, roots=["n1"])

    result = verify_proof_bundle(bundle)

    assert result.valid_bundle is False
    assert result.invalid_nodes == ["n1"]
    assert any(item["code"] == "certificate_error" for item in result.diagnostics)


def test_unsupported_schema_version_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported proof bundle schema version"):
        ProofBundle.from_dict({"schema_version": "9.0", "roots": [], "nodes": []})


def test_consumer_side_recheck_from_json_transport() -> None:
    producer_bundle = create_proof_bundle(nodes={"root": certify("P |- P")}, roots=["root"])
    transport_payload = producer_bundle.to_json()

    consumer_bundle = ProofBundle.from_json(transport_payload)
    consumer_result = verify_proof_bundle(consumer_bundle)

    assert consumer_result.valid_bundle is True
    assert consumer_result.complete is True


def test_transport_corruption_is_rejected_during_json_parse() -> None:
    with pytest.raises(ValueError, match="Invalid proof bundle JSON"):
        ProofBundle.from_json("{corrupt json")
