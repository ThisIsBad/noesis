"""Metamorphic tests for proof certificates (Issue #31)."""

from __future__ import annotations

import pytest

from logos import ProofCertificate, certify, verify_certificate


pytestmark = pytest.mark.metamorphic


@pytest.mark.parametrize(
    "argument",
    [
        "P -> Q, P |- Q",
        "P -> Q, Q |- P",
        "~(P & Q), P |- ~Q",
    ],
)
def test_mr_c1_certificate_roundtrip_preserves_reverification(argument: str) -> None:
    cert = certify(argument)
    restored = ProofCertificate.from_json(cert.to_json())

    assert verify_certificate(cert) is True
    assert verify_certificate(restored) is True
    assert restored.verified is cert.verified


@pytest.mark.parametrize(
    ("source_argument", "equivalent_argument"),
    [
        ("P -> Q, P |- Q", "(~P | Q), P |- Q"),
        ("~(P & Q), P |- ~Q", "(~P | ~Q), P |- ~Q"),
        ("P -> Q, Q |- P", "(~P | Q), Q |- P"),
    ],
)
def test_mr_c2_equivalent_transforms_preserve_certificate_validity(
    source_argument: str,
    equivalent_argument: str,
) -> None:
    source_cert = certify(source_argument)
    equivalent_cert = certify(equivalent_argument)

    assert source_cert.verified is equivalent_cert.verified


@pytest.mark.parametrize(
    ("source_argument", "argument_with_redundant_premise"),
    [
        ("P -> Q, P |- Q", "P -> Q, P, P |- Q"),
        ("P -> Q, Q |- P", "P -> Q, Q, Q |- P"),
        ("P | Q, ~P |- Q", "P | Q, ~P, ~P |- Q"),
    ],
)
def test_mr_c3_redundant_premises_preserve_certificate_validity(
    source_argument: str,
    argument_with_redundant_premise: str,
) -> None:
    source_cert = certify(source_argument)
    redundant_cert = certify(argument_with_redundant_premise)

    assert source_cert.verified is redundant_cert.verified
