"""Tests for the verified agent runtime."""

from __future__ import annotations

from collections.abc import Mapping

from logos import (
    ActionEnvelope,
    ActionPolicyEngine,
    ActionPolicyRule,
    GoalContract,
    PostconditionCheck,
    RiskLevel,
    RuntimePhase,
    RuntimeRequest,
    VerifiedAgentRuntime,
    certify,
    CounterfactualPlanner,
)
from logos.execution_bus import ToolAdapter


def _planner() -> CounterfactualPlanner:
    planner = CounterfactualPlanner()
    planner.declare("x", "Int")
    planner.assert_constraint("x > 0")
    planner.branch("safe", additional_constraints=["x < 10"])
    planner.branch("bad", additional_constraints=["x < 0"])
    return planner


def _valid_adapter(payload: Mapping[str, object]) -> dict[str, object]:
    _ = payload
    return {"valid": True}


def _invalid_adapter(payload: Mapping[str, object]) -> dict[str, object]:
    _ = payload
    return {"valid": False}


def test_runtime_executes_only_after_all_core_gates_pass() -> None:
    planner = _planner()
    runtime = VerifiedAgentRuntime(planner)
    request = RuntimeRequest(
        request_id="req-1",
        branch_id="safe",
        strategy="default",
        contract=GoalContract(contract_id="ship", preconditions=("sat",), invariants=("sat",)),
        action_envelope=ActionEnvelope(
            intent="verify a safe claim",
            action="verify_argument",
            payload={"argument": "P |- P"},
            expected_postconditions=(),
        ),
        proof_certificate=certify("P |- P"),
        risk_level=RiskLevel.LOW,
    )

    outcome = runtime.run(request, adapters={"verify_argument": _valid_adapter})

    assert outcome.phase is RuntimePhase.COMPLETED
    assert outcome.completed is True
    assert outcome.blocked is False
    assert [event.phase for event in outcome.trace.events] == [
        RuntimePhase.PLANNING,
        RuntimePhase.CONTRACT,
        RuntimePhase.UNCERTAINTY,
        RuntimePhase.EXECUTION,
        RuntimePhase.COMPLETED,
    ]


def test_runtime_blocks_high_risk_action_without_uncertainty_compliance() -> None:
    planner = _planner()
    runtime = VerifiedAgentRuntime(planner)
    request = RuntimeRequest(
        request_id="req-2",
        branch_id="safe",
        strategy="default",
        contract=GoalContract(contract_id="ship", preconditions=("sat",), invariants=("sat",)),
        action_envelope=ActionEnvelope(intent="unsafe", action="verify_argument", payload={"argument": "P |- P"}),
        proof_certificate=certify("P -> Q, Q |- P"),
        risk_level=RiskLevel.HIGH,
    )

    outcome = runtime.run(request, adapters={"verify_argument": _valid_adapter})

    assert outcome.phase is RuntimePhase.BLOCKED
    assert outcome.recovery_decision is not None
    assert outcome.recovery_decision.selected_protocol.value == "escalate"
    assert outcome.action_result is None


def test_runtime_failure_handling_uses_recovery_protocols() -> None:
    planner = _planner()
    runtime = VerifiedAgentRuntime(planner)
    request = RuntimeRequest(
        request_id="req-3",
        branch_id="safe",
        strategy="default",
        contract=GoalContract(contract_id="ship", preconditions=("sat",), invariants=("sat",)),
        action_envelope=ActionEnvelope(
            intent="verify a risky claim",
            action="verify_argument",
            payload={"argument": "P -> Q, Q |- P"},
            expected_postconditions=(PostconditionCheck(path="valid", equals=True),),
        ),
        proof_certificate=certify("P |- P"),
        risk_level=RiskLevel.LOW,
    )

    outcome = runtime.run(
        request,
        adapters={"verify_argument": _invalid_adapter},
    )

    assert outcome.phase is RuntimePhase.BLOCKED
    assert outcome.recovery_decision is not None
    assert outcome.recovery_decision.selected_protocol.value == "rollback"
    assert outcome.trace.events[-1].phase is RuntimePhase.RECOVERY


def test_runtime_replay_reproduces_trace_and_outcome() -> None:
    planner = _planner()
    runtime = VerifiedAgentRuntime(planner)
    request = RuntimeRequest(
        request_id="req-4",
        branch_id="safe",
        strategy="default",
        contract=GoalContract(contract_id="ship", preconditions=("sat",), invariants=("sat",)),
        action_envelope=ActionEnvelope(intent="verify", action="verify_argument", payload={"argument": "P |- P"}),
        proof_certificate=certify("P |- P"),
        risk_level=RiskLevel.LOW,
    )
    adapters: dict[str, ToolAdapter] = {"verify_argument": _valid_adapter}

    first = runtime.run(request, adapters)
    replayed = runtime.replay(request, adapters, first.trace)

    assert replayed.phase is first.phase is RuntimePhase.COMPLETED
    assert replayed.trace.to_dict() == first.trace.to_dict()


def test_runtime_long_horizon_sequence_keeps_all_actions_verified() -> None:
    planner = _planner()
    policy_engine = ActionPolicyEngine(
        [ActionPolicyRule(name="block_unsafe", severity="error", message="unsafe", when_true=("unsafe",))]
    )
    runtime = VerifiedAgentRuntime(planner, policy_engine=policy_engine)
    requests = [
        RuntimeRequest(
            request_id="req-a",
            branch_id="safe",
            strategy="default",
            contract=GoalContract(contract_id="ship", preconditions=("sat",), invariants=("sat",)),
            action_envelope=ActionEnvelope(intent="step1", action="verify_argument", payload={"argument": "P |- P"}),
            proof_certificate=certify("P |- P"),
            risk_level=RiskLevel.LOW,
            policy_action={"unsafe": False},
        ),
        RuntimeRequest(
            request_id="req-b",
            branch_id="safe",
            strategy="default",
            contract=GoalContract(contract_id="ship", preconditions=("sat",), invariants=("sat",)),
            action_envelope=ActionEnvelope(intent="step2", action="verify_argument", payload={"argument": "Q |- Q"}),
            proof_certificate=certify("Q |- Q"),
            risk_level=RiskLevel.LOW,
            policy_action={"unsafe": False},
        ),
    ]

    outcomes = [
        runtime.run(request, adapters={"verify_argument": _valid_adapter})
        for request in requests
    ]

    assert all(outcome.completed for outcome in outcomes)
    assert all(
        outcome.action_result is not None and outcome.action_result.status == "completed"
        for outcome in outcomes
    )


def test_runtime_adversarial_policy_case_blocks_before_execution() -> None:
    planner = _planner()
    policy_engine = ActionPolicyEngine(
        [ActionPolicyRule(name="block_unsafe", severity="error", message="unsafe", when_true=("unsafe",))]
    )
    runtime = VerifiedAgentRuntime(planner, policy_engine=policy_engine)
    request = RuntimeRequest(
        request_id="req-5",
        branch_id="safe",
        strategy="default",
        contract=GoalContract(contract_id="ship", preconditions=("sat",), invariants=("sat",)),
        action_envelope=ActionEnvelope(intent="adv", action="verify_argument", payload={"argument": "P |- P"}),
        proof_certificate=certify("P |- P"),
        risk_level=RiskLevel.LOW,
        policy_action={"unsafe": True},
    )

    outcome = runtime.run(request, adapters={"verify_argument": _valid_adapter})

    assert outcome.phase is RuntimePhase.BLOCKED
    assert outcome.contract_result is not None
    assert outcome.contract_result.policy_decision is not None
    assert outcome.action_result is None
