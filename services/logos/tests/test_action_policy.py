"""Tests for action policy enforcement (Issue #35)."""

from __future__ import annotations

import pytest

from logos import (
    ActionPolicyEngine,
    ActionPolicyRule,
    CheckResult,
    PolicyDecision,
)
from logos.action_policy import PolicyCheckStatus


def _engine() -> ActionPolicyEngine:
    return ActionPolicyEngine(
        [
            ActionPolicyRule(
                name="test_coverage",
                severity="error",
                message="Public API changes require tests",
                when_true=("target_is_public_api",),
                when_false=("has_tests",),
            ),
            ActionPolicyRule(
                name="dependency_review",
                severity="warning",
                message="New dependencies require review",
                when_true=("adds_dependency",),
            ),
        ]
    )


def test_deterministic_outcome_for_identical_input() -> None:
    engine = _engine()
    action = {
        "target_is_public_api": True,
        "has_tests": False,
        "adds_dependency": False,
    }

    first = engine.evaluate(action)
    second = engine.evaluate(action)

    assert first == second
    assert first.decision is PolicyDecision.BLOCK


def test_structured_violation_evidence_and_remediation() -> None:
    engine = _engine()

    result = engine.evaluate(
        {
            "target_is_public_api": True,
            "has_tests": False,
            "adds_dependency": True,
        }
    )

    assert result.decision is PolicyDecision.BLOCK
    assert len(result.violations) == 2
    assert result.violations[0].policy_name
    assert result.violations[0].triggered_fields
    assert result.violations[0].z3_witness is not None
    assert result.remediation_hints


def test_review_required_when_only_warning_policies_trigger() -> None:
    engine = _engine()

    result = engine.evaluate(
        {
            "target_is_public_api": False,
            "has_tests": False,
            "adds_dependency": True,
        }
    )

    assert result.decision is PolicyDecision.REVIEW_REQUIRED


def test_allow_when_no_policy_triggers() -> None:
    engine = _engine()

    result = engine.evaluate(
        {
            "target_is_public_api": True,
            "has_tests": True,
            "adds_dependency": False,
        }
    )

    assert result.decision is PolicyDecision.ALLOW
    assert result.violations == []


def test_legacy_policy_compatibility_loader() -> None:
    engine = ActionPolicyEngine.from_legacy_policies(
        [
            {
                "name": "legacy_rule",
                "severity": "error",
                "message": "Legacy block",
                "when_true": ["x"],
                "when_false": ["y"],
            }
        ]
    )

    result = engine.evaluate({"x": True, "y": False})
    assert result.decision is PolicyDecision.BLOCK


def test_serialization_roundtrip_preserves_policy_behavior() -> None:
    engine = _engine()
    restored = ActionPolicyEngine.from_json(engine.to_json())

    action = {
        "target_is_public_api": True,
        "has_tests": False,
        "adds_dependency": True,
    }
    assert engine.evaluate(action) == restored.evaluate(action)


def test_check_policy_consistency_z3_detects_contradictory_rules() -> None:
    engine = ActionPolicyEngine(
        [
            ActionPolicyRule(
                name="requires_manual_approval",
                severity="error",
                message="Manual approval required",
                when_true=("manual_approval",),
            ),
            ActionPolicyRule(
                name="forbids_manual_approval",
                severity="error",
                message="Manual approval must not be used",
                when_false=("manual_approval",),
            ),
            ActionPolicyRule(
                name="independent_warning",
                severity="warning",
                message="Log dependency changes",
                when_true=("adds_dependency",),
            ),
        ]
    )

    contradictions = engine.check_policy_consistency_z3()

    assert contradictions == (("forbids_manual_approval", "requires_manual_approval"),)
    assert contradictions.status is PolicyCheckStatus.OK


def test_check_policy_subsumption_z3_proves_stricter_rule() -> None:
    engine = ActionPolicyEngine()
    broader_rule = ActionPolicyRule(
        name="public_api_change",
        severity="error",
        message="Public API changes require review",
        when_true=("target_is_public_api",),
    )
    narrower_rule = ActionPolicyRule(
        name="public_api_dependency_change",
        severity="error",
        message="Dependency changes on public API require review",
        when_true=("target_is_public_api", "adds_dependency"),
    )

    broader_subsumes_narrower = engine.check_policy_subsumption_z3(broader_rule, narrower_rule)
    narrower_subsumes_broader = engine.check_policy_subsumption_z3(narrower_rule, broader_rule)

    assert broader_subsumes_narrower
    assert broader_subsumes_narrower.witness is not None
    assert not narrower_subsumes_broader


def test_policy_evaluation_surfaces_unknown_solver_state() -> None:
    engine = _engine()

    def fake_check(self: object) -> CheckResult:
        return CheckResult(status="unknown", satisfiable=None, reason="timeout")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("logos.z3_session.Z3Session.check", fake_check)
        result = engine.evaluate(
            {
                "target_is_public_api": False,
                "has_tests": True,
                "adds_dependency": False,
            }
        )

    assert result.decision is PolicyDecision.REVIEW_REQUIRED
    assert result.solver_status == "unknown"
    assert result.reason == "timeout"


def test_policy_subsumption_surfaces_unknown_result() -> None:
    engine = ActionPolicyEngine()
    broader_rule = ActionPolicyRule(
        name="public_api_change",
        severity="error",
        message="Public API changes require review",
        when_true=("target_is_public_api",),
    )
    narrower_rule = ActionPolicyRule(
        name="public_api_dependency_change",
        severity="error",
        message="Dependency changes on public API require review",
        when_true=("target_is_public_api", "adds_dependency"),
    )

    def fake_check(self: object) -> CheckResult:
        return CheckResult(status="unknown", satisfiable=None, reason="timeout")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("logos.z3_session.Z3Session.check", fake_check)
        result = engine.check_policy_subsumption_z3(broader_rule, narrower_rule)

    assert result.subsumed is None
    assert result.status is PolicyCheckStatus.UNKNOWN
    assert result.reason == "timeout"
