"""Tests for proof certificates (Issue #30)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from logos import ProofCertificate, certify, certify_z3_session, verify_certificate
from logos.predicate_models import (
    Constant,
    FOLArgument,
    Predicate,
    PredicateConnective,
    PredicateExpression,
    QuantifiedExpression,
    Quantifier,
    Variable,
)
from logos.z3_session import Z3Session


def _valid_fol_argument() -> FOLArgument:
    x = Variable("x")
    socrates = Constant("Socrates")
    man_x = Predicate("Man", (x,))
    mortal_x = Predicate("Mortal", (x,))
    premise_1 = QuantifiedExpression(
        Quantifier.FORALL,
        x,
        PredicateExpression(PredicateConnective.IMPLIES, man_x, mortal_x),
    )
    premise_2 = Predicate("Man", (socrates,))
    conclusion = Predicate("Mortal", (socrates,))
    return FOLArgument(premises=(premise_1, premise_2), conclusion=conclusion)


def _invalid_fol_argument() -> FOLArgument:
    x = Variable("x")
    socrates = Constant("Socrates")
    man_x = Predicate("Man", (x,))
    mortal_x = Predicate("Mortal", (x,))
    premise_1 = QuantifiedExpression(
        Quantifier.FORALL,
        x,
        PredicateExpression(PredicateConnective.IMPLIES, man_x, mortal_x),
    )
    premise_2 = Predicate("Mortal", (socrates,))
    conclusion = Predicate("Man", (socrates,))
    return FOLArgument(premises=(premise_1, premise_2), conclusion=conclusion)


def test_certify_propositional_valid_claim() -> None:
    cert = certify("P -> Q, P |- Q")

    assert cert.claim_type == "propositional"
    assert cert.method == "z3_propositional"
    assert cert.verified is True
    assert cert.timestamp
    assert "rule" in cert.verification_artifact


def test_certify_propositional_invalid_claim() -> None:
    cert = certify("P -> Q, Q |- P")

    assert cert.claim_type == "propositional"
    assert cert.verified is False


def test_verify_certificate_rechecks_propositional_result() -> None:
    cert = certify("P -> Q, P |- Q")

    assert verify_certificate(cert) is True


def test_verify_certificate_detects_tampered_propositional_verified_flag() -> None:
    cert = certify("P -> Q, P |- Q")
    tampered = replace(cert, verified=False)

    assert verify_certificate(tampered) is False


def test_certificate_json_roundtrip_for_propositional() -> None:
    cert = certify("P -> Q, P |- Q")
    restored = ProofCertificate.from_json(cert.to_json())

    assert restored == cert
    assert verify_certificate(restored) is True


def test_certificate_from_json_rejects_invalid_payload() -> None:
    with pytest.raises(ValueError, match="Invalid certificate JSON"):
        ProofCertificate.from_json("{bad json")


def test_certificate_from_json_rejects_missing_fields() -> None:
    with pytest.raises(ValueError, match="missing fields"):
        ProofCertificate.from_json('{"schema_version":"1.0"}')


def test_certificate_from_json_rejects_unsupported_schema_version() -> None:
    payload = (
        '{'
        '"schema_version":"2.0",'
        '"claim_type":"propositional",'
        '"claim":"P |- P",'
        '"method":"z3_propositional",'
        '"verified":true,'
        '"timestamp":"2026-01-01T00:00:00+00:00",'
        '"verification_artifact":{}'
        '}'
    )
    with pytest.raises(ValueError, match="Unsupported certificate schema version"):
        ProofCertificate.from_json(payload)


def test_certify_fol_valid_claim() -> None:
    cert = certify(_valid_fol_argument())

    assert cert.claim_type == "fol"
    assert cert.method == "z3_fol"
    assert cert.verified is True
    assert verify_certificate(cert) is True


def test_certify_fol_invalid_claim() -> None:
    cert = certify(_invalid_fol_argument())

    assert cert.claim_type == "fol"
    assert cert.verified is False
    assert verify_certificate(cert) is True


def test_certificate_json_roundtrip_for_fol() -> None:
    cert = certify(_valid_fol_argument())
    restored = ProofCertificate.from_json(cert.to_json())

    assert restored == cert
    assert verify_certificate(restored) is True


def test_certify_z3_session_sat_claim() -> None:
    session = Z3Session()
    session.declare("x", "Int")
    session.assert_constraint("x > 0")
    session.assert_constraint("x < 10")

    cert = certify(session)

    assert cert.claim_type == "z3_session"
    assert cert.method == "z3_session"
    assert cert.verified is True
    assert verify_certificate(cert) is True


def test_certify_z3_session_unsat_claim() -> None:
    session = Z3Session()
    session.declare("x", "Int")
    session.assert_constraint("x > 0")
    session.assert_constraint("x < 0")

    cert = certify(session)

    assert cert.claim_type == "z3_session"
    assert cert.verified is False
    assert verify_certificate(cert) is True


def test_certify_z3_session_uses_existing_check_result() -> None:
    session = Z3Session()
    session.declare("x", "Int")
    session.assert_constraint("x > 0")
    check_result = session.check()

    cert = certify_z3_session(session, check_result)

    assert cert.claim_type == "z3_session"
    assert cert.verified is True
    assert cert.verification_artifact["status"] == check_result.status


def test_certificate_json_roundtrip_for_z3_session() -> None:
    session = Z3Session()
    session.declare("x", "Int")
    session.declare("y", "Int")
    session.assert_constraint("x > 0")
    session.assert_constraint("y == x + 1")

    cert = certify(session)
    restored = ProofCertificate.from_json(cert.to_json())

    assert restored == cert
    assert verify_certificate(restored) is True


def test_verify_certificate_rejects_unknown_claim_type() -> None:
    cert = ProofCertificate(
        schema_version="1.0",
        claim_type="unknown",
        claim="P |- P",
        method="none",
        verified=True,
        timestamp="2026-01-01T00:00:00+00:00",
        verification_artifact={},
    )

    with pytest.raises(ValueError, match="Unknown certificate claim_type"):
        verify_certificate(cert)


def test_certify_rejects_unsupported_input_type() -> None:
    with pytest.raises(TypeError, match="Unsupported claim type"):
        certify(123)  # type: ignore[arg-type]
