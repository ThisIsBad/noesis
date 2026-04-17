"""Metamorphic tests for recovery protocol selection."""

from __future__ import annotations

import pytest

from logos import FailureCategory, FailureContext, RecoveryProtocol, choose_recovery


pytestmark = pytest.mark.metamorphic


def test_mr_rp01_equivalent_failure_contexts_preserve_allowed_protocols() -> None:
    first = FailureContext(
        category=FailureCategory.PRECONDITION_FAILURE,
        source="execution_bus",
        retry_count=0,
        max_retries=2,
        details={"diagnostic_codes": ["missing_precondition_certificate"], "status": "rejected_preconditions"},
    )
    second = FailureContext(
        category=FailureCategory.PRECONDITION_FAILURE,
        source="execution_bus",
        retry_count=0,
        max_retries=2,
        details={"status": "rejected_preconditions", "diagnostic_codes": ["missing_precondition_certificate"]},
    )

    first_decision = choose_recovery(first)
    second_decision = choose_recovery(second)

    assert first_decision.allowed_protocols == second_decision.allowed_protocols
    assert first_decision.selected_protocol == second_decision.selected_protocol == RecoveryProtocol.RETRY


def test_mr_rp02_retry_guard_equivalence_preserves_non_retry_protocols() -> None:
    first = FailureContext(
        category=FailureCategory.PROOF_FAILURE,
        source="orchestrator",
        retry_count=3,
        max_retries=3,
    )
    second = FailureContext(
        category=FailureCategory.PROOF_FAILURE,
        source="orchestrator",
        retry_count=4,
        max_retries=3,
    )

    first_decision = choose_recovery(first)
    second_decision = choose_recovery(second)

    assert RecoveryProtocol.RETRY not in first_decision.allowed_protocols
    assert RecoveryProtocol.RETRY not in second_decision.allowed_protocols
    assert first_decision.allowed_protocols == second_decision.allowed_protocols
    assert first_decision.selected_protocol == second_decision.selected_protocol == RecoveryProtocol.REPLAN
