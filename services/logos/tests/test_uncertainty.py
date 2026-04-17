"""Tests for uncertainty calibration and escalation (Issue #36)."""

from __future__ import annotations

from logos import (
    EscalationDecision,
    RiskLevel,
    UncertaintyCalibrator,
    certificate_reference,
    certify,
    resolve_certificate_reference,
)
from logos.uncertainty import ConfidenceLevel, ConfidenceRecord


def test_confidence_record_json_roundtrip() -> None:
    record = ConfidenceRecord(
        claim="x > 0",
        level=ConfidenceLevel.SUPPORTED,
        provenance=("z3_propositional",),
        linked_certificate_ref=None,
    )

    restored = ConfidenceRecord.from_json(record.to_json())
    assert restored == record


def test_classification_is_deterministic() -> None:
    calibrator = UncertaintyCalibrator()

    first = calibrator.classify(verified=True, evidence_count=2, conflicting_signals=False)
    second = calibrator.classify(verified=True, evidence_count=2, conflicting_signals=False)
    assert first is second is ConfidenceLevel.CERTAIN


def test_high_risk_weak_confidence_is_blocked() -> None:
    calibrator = UncertaintyCalibrator()
    record = ConfidenceRecord(
        claim="unsafe refactor",
        level=ConfidenceLevel.WEAK,
        provenance=("single_source",),
    )

    result = calibrator.enforce(record=record, risk_level=RiskLevel.HIGH)
    assert result.decision is EscalationDecision.BLOCKED


def test_medium_risk_supported_confidence_can_proceed() -> None:
    calibrator = UncertaintyCalibrator()
    record = ConfidenceRecord(
        claim="safe change",
        level=ConfidenceLevel.SUPPORTED,
        provenance=("proof_certificate",),
    )

    result = calibrator.enforce(record=record, risk_level=RiskLevel.MEDIUM)
    assert result.decision is EscalationDecision.PROCEED


def test_certificate_integration_produces_confidence_record() -> None:
    calibrator = UncertaintyCalibrator()
    cert = certify("P -> Q, P |- Q")

    record = calibrator.from_certificate(cert, provenance=["z3_propositional", "cross_check"])
    assert record.level is ConfidenceLevel.CERTAIN
    assert record.linked_certificate_ref is not None
    assert record.linked_certificate_ref.startswith("sha256:")


def test_policy_compliance_check_detects_invalid_external_decision() -> None:
    calibrator = UncertaintyCalibrator()
    record = ConfidenceRecord(
        claim="high risk claim",
        level=ConfidenceLevel.WEAK,
        provenance=("single_source",),
    )

    compliant = calibrator.is_policy_compliant(
        record=record,
        risk_level=RiskLevel.HIGH,
        decision=EscalationDecision.BLOCKED,
    )
    non_compliant = calibrator.is_policy_compliant(
        record=record,
        risk_level=RiskLevel.HIGH,
        decision=EscalationDecision.PROCEED,
    )

    assert compliant is True
    assert non_compliant is False


def test_legacy_linked_certificate_payload_is_migrated_to_reference() -> None:
    cert = certify("P |- P")
    payload = {
        "schema_version": "1.0",
        "claim": "P |- P",
        "level": "supported",
        "provenance": ["legacy"],
        "linked_certificate": cert.to_json(),
    }

    record = ConfidenceRecord.from_dict(payload)

    assert record.linked_certificate_ref == certificate_reference(cert)


def test_resolve_certificate_reference_finds_matching_certificate() -> None:
    cert = certify("P -> Q, P |- Q")
    calibrator = UncertaintyCalibrator()
    record = calibrator.from_certificate(cert)

    resolved = resolve_certificate_reference(record, {"any": cert})

    assert resolved == cert
