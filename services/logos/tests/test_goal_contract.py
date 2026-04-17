"""Tests for goal contracts and strategy verification (Issue #44)."""

from __future__ import annotations

import pytest

from logos import (
    ActionPolicyEngine,
    ActionPolicyRule,
    CheckResult,
    CounterfactualPlanner,
    GoalContract,
    GoalContractStatus,
    build_branch_context,
    evaluate_goal_contract,
    verify_contract_preconditions_z3,
)


def _branch_context_sat() -> dict[str, bool]:
    planner = CounterfactualPlanner()
    planner.declare("x", "Int")
    planner.assert_constraint("x > 0")
    branch = planner.branch("b1", additional_constraints=["x < 10"])
    return build_branch_context(branch)


def test_goal_contract_evaluation_is_deterministic() -> None:
    contract = GoalContract(
        contract_id="gc1",
        preconditions=("sat",),
        invariants=("!unsat",),
        completion_criteria=("sat",),
        permitted_strategies=("safe",),
    )
    context = _branch_context_sat()

    first = evaluate_goal_contract(contract, strategy="safe", context=context)
    second = evaluate_goal_contract(contract, strategy="safe", context=context)

    assert first == second
    assert first.status is GoalContractStatus.COMPLETED


def test_goal_contract_blocks_unpermitted_strategy() -> None:
    contract = GoalContract(contract_id="gc1", permitted_strategies=("safe",))

    result = evaluate_goal_contract(contract, strategy="aggressive", context={"sat": True})

    assert result.status is GoalContractStatus.BLOCKED
    assert result.diagnostics[0].code == "strategy_not_permitted"


def test_goal_contract_aborts_on_invariant_drift() -> None:
    contract = GoalContract(contract_id="gc1", invariants=("!unsat",))

    result = evaluate_goal_contract(contract, strategy="safe", context={"unsat": True})

    assert result.status is GoalContractStatus.ABORTED
    assert result.diagnostics[0].code == "invariant_failed"


def test_goal_contract_respects_policy_block() -> None:
    contract = GoalContract(contract_id="gc1")
    engine = ActionPolicyEngine(
        [
            ActionPolicyRule(
                name="must_have_tests",
                severity="error",
                message="Missing tests",
                when_true=("changes_code",),
                when_false=("has_tests",),
            )
        ]
    )

    result = evaluate_goal_contract(
        contract,
        strategy="safe",
        context={"sat": True},
        policy_engine=engine,
        policy_action={"changes_code": True, "has_tests": False},
    )

    assert result.status is GoalContractStatus.BLOCKED
    assert result.diagnostics[0].code == "policy_block"


def test_goal_contract_json_roundtrip() -> None:
    contract = GoalContract(
        contract_id="gc1",
        preconditions=("sat",),
        invariants=("!unsat",),
        completion_criteria=("sat",),
        abort_criteria=("unknown",),
        permitted_strategies=("safe",),
    )

    restored = GoalContract.from_json(contract.to_json())

    assert restored == contract


def test_z3_precondition_check_proves_entailed_preconditions() -> None:
    contract = GoalContract(
        contract_id="gc1",
        preconditions=("x > 0", "x <= 100"),
    )

    result = verify_contract_preconditions_z3(
        contract,
        state_constraints=["x == 42"],
        variables={"x": "Int"},
    )

    assert result.status is GoalContractStatus.ACTIVE
    assert result.diagnostics == ()
    assert result.unsat_core == ()
    assert result.solver_status == "unsat"


def test_z3_precondition_check_detects_unentailed_precondition() -> None:
    contract = GoalContract(
        contract_id="gc1",
        preconditions=("x > 0",),
    )

    result = verify_contract_preconditions_z3(
        contract,
        state_constraints=["x == -5"],
        variables={"x": "Int"},
    )

    assert result.status is GoalContractStatus.BLOCKED
    assert result.diagnostics[0].code == "z3_preconditions_unsat"
    assert result.unsat_core == ("x == -5", "x > 0")
    assert result.solver_status == "unsat"


def test_z3_precondition_check_with_auto_variables() -> None:
    contract = GoalContract(
        contract_id="gc1",
        preconditions=("x > 5",),
    )

    result = verify_contract_preconditions_z3(
        contract,
        state_constraints=["x == 10"],
    )

    assert result.status is GoalContractStatus.ACTIVE


def test_z3_precondition_check_uses_single_query_for_composite_preconditions() -> None:
    contract = GoalContract(
        contract_id="gc1",
        preconditions=("x > 0", "y > x", "y < 10"),
    )

    result = verify_contract_preconditions_z3(
        contract,
        state_constraints=["x == 2", "y == 5"],
        variables={"x": "Int", "y": "Int"},
    )

    assert result.status is GoalContractStatus.ACTIVE
    assert result.solver_status == "unsat"


def test_z3_precondition_check_carries_unsat_core_for_inconsistent_preconditions() -> None:
    contract = GoalContract(
        contract_id="gc1",
        preconditions=("x > 0", "x < 0", "y == 1"),
    )

    result = verify_contract_preconditions_z3(
        contract,
        state_constraints=["y == 1"],
        variables={"x": "Int", "y": "Int"},
    )

    assert result.status is GoalContractStatus.BLOCKED
    assert result.diagnostics[0].code == "z3_preconditions_unsat"
    assert result.unsat_core == ("x > 0", "x < 0")
    assert result.solver_status == "unsat"


def test_z3_precondition_check_surfaces_unknown_result(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = GoalContract(contract_id="gc1", preconditions=("x * x == 2",))

    def fake_check(self: object) -> CheckResult:
        return CheckResult(status="unknown", satisfiable=None, reason="timeout")

    monkeypatch.setattr("logos.z3_session.Z3Session.check", fake_check)

    result = verify_contract_preconditions_z3(
        contract,
        state_constraints=["x >= 0"],
        variables={"x": "Int"},
    )

    assert result.status is GoalContractStatus.BLOCKED
    assert result.diagnostics[0].code == "z3_precondition_unknown"
    assert result.reason == "timeout"
    assert result.solver_status == "unknown"
