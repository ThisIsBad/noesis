"""Tests for counterfactual planning (Issue #34)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from unittest.mock import patch

import pytest

from logos import CounterfactualPlanner, SafetyBound, UtilityModel
from logos.z3_session import Z3Session


def _new_planner() -> CounterfactualPlanner:
    planner = CounterfactualPlanner()
    planner.declare("x", "Int")
    planner.assert_constraint("x > 0")
    return planner


def test_sibling_branches_are_isolated() -> None:
    planner = _new_planner()

    branch_unsat = planner.branch("b1", additional_constraints=["x < 0"])
    branch_sat = planner.branch("b2", additional_constraints=["x < 10"])

    assert branch_unsat.status == "unsat"
    assert branch_unsat.model is None
    assert branch_sat.status == "sat"
    assert branch_sat.model is not None
    assert "x" in branch_sat.model


def test_branch_from_parent_inherits_state_without_mutating_parent() -> None:
    planner = _new_planner()

    parent = planner.branch("parent", additional_constraints=["x < 10"])
    child = planner.branch("child", parent_id="parent", additional_constraints=["x > 100"])
    replay_parent = planner.replay("parent")

    assert parent.status == "sat"
    assert child.status == "unsat"
    assert replay_parent.status == "sat"


def test_branch_replay_is_deterministic() -> None:
    planner = _new_planner()
    branch = planner.branch("b1", additional_constraints=["x < 10"])

    replay_a = planner.replay("b1")
    replay_b = planner.replay("b1")

    assert replay_a.status == branch.status == replay_b.status
    assert replay_a.satisfiable is branch.satisfiable is replay_b.satisfiable
    assert replay_a.model == branch.model == replay_b.model


def test_branch_certificates_are_independently_reverifiable() -> None:
    planner = _new_planner()
    planner.branch("sat_branch", additional_constraints=["x < 10"])
    planner.branch("unsat_branch", additional_constraints=["x < 0"])

    assert planner.verify_branch_certificate("sat_branch") is True
    assert planner.verify_branch_certificate("unsat_branch") is True


def test_scoring_hooks_attach_scores() -> None:
    planner = _new_planner()
    branch = planner.branch("b1", additional_constraints=["x < 10"])

    def sat_score(target) -> float:  # type: ignore[no-untyped-def]
        return 1.0 if target.satisfiable is True else 0.0

    scored = planner.score_branch("b1", {"sat_score": sat_score})

    assert scored is not branch
    assert scored.scores["sat_score"] == 1.0
    assert "sat_score" not in branch.scores


def test_unknown_parent_branch_rejected() -> None:
    planner = _new_planner()

    with pytest.raises(ValueError, match="Unknown parent branch"):
        planner.branch("b1", parent_id="missing", additional_constraints=["x < 10"])


def test_external_branch_mutation_is_rejected() -> None:
    planner = _new_planner()
    branch = planner.branch("b1", additional_constraints=["x < 10"])

    with pytest.raises(FrozenInstanceError):
        branch.status = "unsat"  # type: ignore[misc]

    with pytest.raises(TypeError):
        branch.scores["tamper"] = 1.0  # type: ignore[index]


def test_result_snapshot_dict_mutation_does_not_affect_internal_state() -> None:
    planner = _new_planner()
    planner.branch("b1", additional_constraints=["x < 10"])

    snapshot = planner.result()
    snapshot.branches.pop("b1")

    assert planner.get_branch("b1").status == "sat"


def test_branch_evaluation_calls_solver_check_once() -> None:
    planner = _new_planner()

    with patch.object(
        Z3Session,
        "check",
        autospec=True,
        wraps=Z3Session.check,
    ) as wrapped_check:
        planner.branch("b1", additional_constraints=["x < 10"])

    assert wrapped_check.call_count == 1


def test_rank_branches_orders_feasible_branches_by_total_score() -> None:
    planner = _new_planner()
    planner.branch("high", additional_constraints=["x < 10"])
    planner.branch("low", additional_constraints=["x < 20"])
    planner.branch("blocked", additional_constraints=["x < 0"])

    ranked = planner.rank_branches(
        {
            "high": UtilityModel(expected_value=10.0, execution_cost=2.0, risk_penalty=1.0, confidence_weight=1.0),
            "low": UtilityModel(expected_value=7.0, execution_cost=2.0, risk_penalty=1.0, confidence_weight=1.0),
            "blocked": UtilityModel(expected_value=100.0, execution_cost=0.0, risk_penalty=0.0, confidence_weight=1.0),
        }
    )

    assert [item.branch_id for item in ranked] == ["high", "low", "blocked"]
    assert ranked[0].rank == 1
    assert ranked[0].decomposition["total_score"] == 7.0
    assert ranked[2].admissible is False
    assert ranked[2].safety_violations == ("branch_not_feasible",)


def test_rank_branches_hard_safety_caps_dominate_utility() -> None:
    planner = _new_planner()
    planner.branch("fast", additional_constraints=["x < 10"])
    planner.branch("risky", additional_constraints=["x < 20"])

    ranked = planner.rank_branches(
        {
            "fast": UtilityModel(expected_value=8.0, execution_cost=3.0, risk_penalty=1.0, confidence_weight=1.0),
            "risky": UtilityModel(expected_value=100.0, execution_cost=2.0, risk_penalty=20.0, confidence_weight=1.0),
        },
        safety_bounds=SafetyBound(max_risk_penalty=5.0),
    )

    assert [item.branch_id for item in ranked] == ["fast", "risky"]
    assert ranked[0].rank == 1
    assert ranked[1].rank is None
    assert ranked[1].safety_violations == ("risk_penalty_exceeds_cap",)


def test_rank_branches_replay_preserves_ranking_order() -> None:
    planner = _new_planner()
    planner.branch("a", additional_constraints=["x < 10"])
    planner.branch("b", additional_constraints=["x < 20"])
    utility_models = {
        "a": UtilityModel(expected_value=8.0, execution_cost=2.0, risk_penalty=1.0, confidence_weight=1.0),
        "b": UtilityModel(expected_value=9.0, execution_cost=3.0, risk_penalty=1.0, confidence_weight=1.0),
    }

    first = planner.rank_branches(utility_models)
    replayed = planner.replay("a")
    assert replayed.status == "sat"
    second = planner.rank_branches(utility_models)

    assert [(item.branch_id, item.rank) for item in first] == [(item.branch_id, item.rank) for item in second]
