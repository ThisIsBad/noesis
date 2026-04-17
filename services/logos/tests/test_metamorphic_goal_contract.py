"""Metamorphic tests for goal contract evaluation (Issue #44)."""

from __future__ import annotations

import pytest

from logos import GoalContract, GoalContractStatus, evaluate_goal_contract, verify_contract_preconditions_z3


pytestmark = pytest.mark.metamorphic


def test_mr_gc01_equivalent_clause_formulations_preserve_outcome() -> None:
    context = {"sat": True, "unsat": False}
    contract_a = GoalContract(
        contract_id="a",
        invariants=("sat",),
        completion_criteria=("sat",),
    )
    contract_b = GoalContract(
        contract_id="b",
        invariants=("!unsat",),
        completion_criteria=("sat",),
    )

    result_a = evaluate_goal_contract(contract_a, strategy="safe", context=context)
    result_b = evaluate_goal_contract(contract_b, strategy="safe", context=context)

    assert result_a.status is result_b.status is GoalContractStatus.COMPLETED


def test_mr_gc02_clause_order_invariance() -> None:
    context = {"sat": True, "ready": True, "unsat": False}
    ordered = GoalContract(
        contract_id="ordered",
        preconditions=("sat", "ready"),
        invariants=("!unsat", "sat"),
        completion_criteria=("sat",),
    )
    reordered = GoalContract(
        contract_id="reordered",
        preconditions=("ready", "sat"),
        invariants=("sat", "!unsat"),
        completion_criteria=("sat",),
    )

    result_a = evaluate_goal_contract(ordered, strategy="safe", context=context)
    result_b = evaluate_goal_contract(reordered, strategy="safe", context=context)

    assert result_a.status == result_b.status


def test_mr_gc03_redundant_tautological_precondition_does_not_change_z3_result() -> None:
    baseline = GoalContract(contract_id="baseline", preconditions=("x > 0",))
    redundant = GoalContract(contract_id="redundant", preconditions=("x > 0", "x == x"))

    baseline_result = verify_contract_preconditions_z3(
        baseline,
        state_constraints=["x == 5"],
        variables={"x": "Int"},
    )
    redundant_result = verify_contract_preconditions_z3(
        redundant,
        state_constraints=["x == 5"],
        variables={"x": "Int"},
    )

    assert baseline_result.status is redundant_result.status is GoalContractStatus.ACTIVE
    assert baseline_result.solver_status == redundant_result.solver_status


def test_mr_gc04_z3_precondition_evaluation_is_deterministic_across_repeats() -> None:
    contract = GoalContract(contract_id="repeat", preconditions=("x > 0", "x < 10"))

    first = verify_contract_preconditions_z3(
        contract,
        state_constraints=["x == 4"],
        variables={"x": "Int"},
    )
    second = verify_contract_preconditions_z3(
        contract,
        state_constraints=["x == 4"],
        variables={"x": "Int"},
    )

    assert first == second
