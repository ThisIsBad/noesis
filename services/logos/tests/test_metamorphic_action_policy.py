"""Metamorphic tests for action policy enforcement (Issue #35)."""

from __future__ import annotations

import pytest

from logos import ActionPolicyEngine, ActionPolicyRule, PolicyDecision


pytestmark = pytest.mark.metamorphic


def _decision_rank(decision: PolicyDecision) -> int:
    if decision is PolicyDecision.ALLOW:
        return 0
    if decision is PolicyDecision.REVIEW_REQUIRED:
        return 1
    return 2


def test_mr_ap01_removing_policy_cannot_introduce_new_violations() -> None:
    full = ActionPolicyEngine(
        [
            ActionPolicyRule(
                name="rule_a",
                severity="error",
                message="A",
                when_true=("a",),
            ),
            ActionPolicyRule(
                name="rule_b",
                severity="warning",
                message="B",
                when_true=("b",),
            ),
        ]
    )
    reduced = ActionPolicyEngine(
        [
            ActionPolicyRule(
                name="rule_a",
                severity="error",
                message="A",
                when_true=("a",),
            )
        ]
    )

    action = {"a": True, "b": True}
    full_result = full.evaluate(action)
    reduced_result = reduced.evaluate(action)

    assert len(reduced_result.violations) <= len(full_result.violations)
    assert _decision_rank(reduced_result.decision) <= _decision_rank(full_result.decision)


def test_mr_ap02_evaluation_order_does_not_change_decision() -> None:
    ordered = ActionPolicyEngine(
        [
            ActionPolicyRule(
                name="rule_a",
                severity="warning",
                message="A",
                when_true=("a",),
            ),
            ActionPolicyRule(
                name="rule_b",
                severity="error",
                message="B",
                when_true=("b",),
            ),
        ]
    )
    reversed_engine = ActionPolicyEngine(
        [
            ActionPolicyRule(
                name="rule_b",
                severity="error",
                message="B",
                when_true=("b",),
            ),
            ActionPolicyRule(
                name="rule_a",
                severity="warning",
                message="A",
                when_true=("a",),
            ),
        ]
    )

    action = {"a": True, "b": True}

    assert ordered.evaluate(action).decision is reversed_engine.evaluate(action).decision


def test_mr_ap03_rule_order_does_not_change_z3_consistency_or_evaluation() -> None:
    ordered = ActionPolicyEngine(
        [
            ActionPolicyRule(
                name="rule_a",
                severity="warning",
                message="A",
                when_true=("a",),
            ),
            ActionPolicyRule(
                name="rule_b",
                severity="error",
                message="B",
                when_true=("b",),
                when_false=("a",),
            ),
        ]
    )
    reversed_engine = ActionPolicyEngine(
        [
            ActionPolicyRule(
                name="rule_b",
                severity="error",
                message="B",
                when_true=("b",),
                when_false=("a",),
            ),
            ActionPolicyRule(
                name="rule_a",
                severity="warning",
                message="A",
                when_true=("a",),
            ),
        ]
    )

    action = {"a": False, "b": True}

    assert ordered.check_policy_consistency_z3().pairs == reversed_engine.check_policy_consistency_z3().pairs
    assert ordered.evaluate(action).decision is reversed_engine.evaluate(action).decision


def test_mr_ap04_adding_subsumed_rule_does_not_change_any_evaluation_result() -> None:
    baseline = ActionPolicyEngine(
        [
            ActionPolicyRule(
                name="base_rule",
                severity="error",
                message="Base",
                when_true=("target_is_public_api",),
            )
        ]
    )
    augmented = ActionPolicyEngine(
        [
            ActionPolicyRule(
                name="base_rule",
                severity="error",
                message="Base",
                when_true=("target_is_public_api",),
            ),
            ActionPolicyRule(
                name="subsumed_rule",
                severity="error",
                message="Subsumed",
                when_true=("target_is_public_api", "adds_dependency"),
            ),
        ]
    )

    for action in (
        {"target_is_public_api": True, "adds_dependency": False},
        {"target_is_public_api": True, "adds_dependency": True},
        {"target_is_public_api": False, "adds_dependency": True},
    ):
        assert baseline.evaluate(action).decision is augmented.evaluate(action).decision
