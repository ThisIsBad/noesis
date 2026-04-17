"""Tests for deterministic recovery protocols."""

from __future__ import annotations

from logos import (
    ActionEnvelope,
    FailureCategory,
    FailureContext,
    GoalContract,
    GoalContractStatus,
    ProofOrchestrator,
    RecoveryProtocol,
    choose_recovery,
    classify_action_bus_failure,
    classify_claim_failure,
    classify_goal_contract_failure,
    classify_plan_failure,
    evaluate_goal_contract,
    execute_action_envelope,
    failure_context_from_dict,
    verify_recovery_certificate,
)
from logos.action_policy import ActionPolicyEngine, ActionPolicyRule


def test_all_failure_categories_have_default_protocol_mapping() -> None:
    for category in FailureCategory:
        context = FailureContext(category=category, source="test")
        decision = choose_recovery(context)
        assert decision.allowed_protocols
        assert decision.selected_protocol in decision.allowed_protocols


def test_choose_recovery_is_deterministic_and_auditable() -> None:
    context = FailureContext(
        category=FailureCategory.POSTCONDITION_FAILURE,
        source="execution_bus",
        retry_count=0,
        max_retries=1,
        details={"status": "postcondition_mismatch"},
    )

    first = choose_recovery(context)
    second = choose_recovery(context)

    assert first.allowed_protocols == second.allowed_protocols
    assert first.selected_protocol == second.selected_protocol == RecoveryProtocol.ROLLBACK
    assert first.trace == second.trace
    assert verify_recovery_certificate(first.certificate) is True


def test_retry_guard_removes_retry_when_limit_reached() -> None:
    context = FailureContext(
        category=FailureCategory.PRECONDITION_FAILURE,
        source="execution_bus",
        retry_count=2,
        max_retries=2,
    )

    decision = choose_recovery(context)

    assert RecoveryProtocol.RETRY not in decision.allowed_protocols
    assert decision.guard_triggered is True
    assert decision.selected_protocol == RecoveryProtocol.ESCALATE


def test_classify_action_bus_failure_maps_to_precondition_category() -> None:
    envelope = ActionEnvelope(
        intent="verify a claim",
        action="verify_argument",
        payload={"argument": "P |- P"},
        preconditions=("missing",),
    )
    result = execute_action_envelope(envelope, adapters={"verify_argument": lambda payload: {"valid": True}})

    context = classify_action_bus_failure(result, retry_count=1, max_retries=2)

    assert context.category is FailureCategory.PRECONDITION_FAILURE
    assert context.details["diagnostic_codes"] == ["missing_precondition_certificate"]


def test_classify_claim_failure_distinguishes_proof_and_composition_failures() -> None:
    orchestrator = ProofOrchestrator()
    orchestrator.claim("root", "Main claim")
    orchestrator.sub_claim("leaf", "root", "Leaf claim")
    orchestrator.verify_leaf("leaf", "P -> Q, Q |- P")
    proof_context = classify_claim_failure(orchestrator.get_claim("leaf"))

    orchestrator.set_composition("root", "leaf")
    orchestrator.propagate()
    composition_context = classify_claim_failure(orchestrator.get_claim("root"))

    assert proof_context.category is FailureCategory.PROOF_FAILURE
    assert composition_context.category is FailureCategory.COMPOSITION_FAILURE


def test_classify_plan_failure_maps_unsat_branch_to_replan() -> None:
    from logos import CounterfactualPlanner

    planner = CounterfactualPlanner()
    planner.declare("x", "Int")
    planner.assert_constraint("x > 0")
    branch = planner.branch("bad", additional_constraints=["x < 0"])

    context = classify_plan_failure(branch)
    decision = choose_recovery(context)

    assert context.category is FailureCategory.PLAN_INFEASIBLE
    assert decision.selected_protocol is RecoveryProtocol.REPLAN


def test_classify_goal_contract_failure_maps_policy_block() -> None:
    contract = GoalContract(contract_id="deploy", preconditions=("sat",))
    policy = ActionPolicyEngine(
        [ActionPolicyRule(name="block", severity="error", message="stop", when_true=("unsafe",))]
    )
    result = evaluate_goal_contract(
        contract,
        strategy="default",
        context={"sat": True, "unsafe": True},
        policy_engine=policy,
        policy_action={"unsafe": True},
    )

    context = classify_goal_contract_failure(result)

    assert result.status is GoalContractStatus.BLOCKED
    assert context.category is FailureCategory.POLICY_BLOCK


def test_failure_context_roundtrip_preserves_fields() -> None:
    original = FailureContext(
        category=FailureCategory.PLAN_UNKNOWN,
        source="counterfactual",
        retry_count=1,
        max_retries=3,
        details={"branch_id": "x"},
    )

    restored = failure_context_from_dict(original.to_dict())

    assert restored == original
