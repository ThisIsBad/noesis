"""Metamorphic tests for uncertainty policy behavior (Issue #36)."""

from __future__ import annotations

import pytest

from logos import EscalationDecision, RiskLevel, UncertaintyCalibrator
from logos.uncertainty import ConfidenceLevel, ConfidenceRecord


pytestmark = pytest.mark.metamorphic


def _decision_rank(decision: EscalationDecision) -> int:
    if decision is EscalationDecision.PROCEED:
        return 0
    if decision is EscalationDecision.REVIEW_REQUIRED:
        return 1
    return 2


def test_mr_u01_increasing_risk_does_not_reduce_strictness() -> None:
    calibrator = UncertaintyCalibrator()
    record = ConfidenceRecord(
        claim="claim",
        level=ConfidenceLevel.SUPPORTED,
        provenance=("proof",),
    )

    low = calibrator.enforce(record=record, risk_level=RiskLevel.LOW)
    medium = calibrator.enforce(record=record, risk_level=RiskLevel.MEDIUM)
    high = calibrator.enforce(record=record, risk_level=RiskLevel.HIGH)

    assert _decision_rank(low.decision) <= _decision_rank(medium.decision)
    assert _decision_rank(medium.decision) <= _decision_rank(high.decision)


def test_mr_u02_provenance_order_does_not_change_escalation() -> None:
    calibrator = UncertaintyCalibrator()
    first = ConfidenceRecord(
        claim="claim",
        level=ConfidenceLevel.WEAK,
        provenance=("source_a", "source_b"),
    )
    second = ConfidenceRecord(
        claim="claim",
        level=ConfidenceLevel.WEAK,
        provenance=("source_b", "source_a"),
    )

    first_decision = calibrator.enforce(record=first, risk_level=RiskLevel.HIGH)
    second_decision = calibrator.enforce(record=second, risk_level=RiskLevel.HIGH)

    assert first_decision.decision is second_decision.decision
