"""Metamorphic tests for proof exchange protocol (Issue #37)."""

from __future__ import annotations

import pytest

from logos import ProofBundle, create_proof_bundle, certify, verify_proof_bundle


pytestmark = pytest.mark.metamorphic


def test_mr_px01_node_order_invariance() -> None:
    cert_a = certify("P -> Q, P |- Q")
    cert_b = certify("P -> Q, Q |- P")

    ordered = create_proof_bundle(nodes={"a": cert_a, "b": cert_b}, dependencies={"b": ["a"]}, roots=["b"])
    reordered = create_proof_bundle(nodes={"b": cert_b, "a": cert_a}, dependencies={"b": ["a"]}, roots=["b"])

    assert verify_proof_bundle(ordered) == verify_proof_bundle(reordered)


def test_mr_px02_adding_independent_valid_node_preserves_validity() -> None:
    base = create_proof_bundle(nodes={"root": certify("P |- P")}, roots=["root"])

    extended_payload = base.to_dict()
    nodes = extended_payload["nodes"]
    assert isinstance(nodes, list)
    nodes.append(
        {
            "node_id": "independent",
            "certificate": certify("Q |- Q").to_dict(),
            "depends_on": [],
        }
    )

    extended = ProofBundle.from_dict(extended_payload)

    assert verify_proof_bundle(base).valid_bundle is True
    assert verify_proof_bundle(extended).valid_bundle is True
