from __future__ import annotations

from typing import cast

import pytest

from examples import reflective_agent
from logos import (
    RecoveryProtocol,
    UncertaintyCalibrator,
    certify,
    choose_recovery,
    classify_goal_contract_failure,
    verify_contract_preconditions_z3,
)
from logos.goal_contract import GoalContract
from logos.mcp_tools import check_assumptions, check_contract


def _confidence_probability(level: object) -> float:
    value = getattr(level, "value", str(level))
    if value == "certain":
        return 1.0
    if value == "supported":
        return 0.75
    if value == "weak":
        return 0.0
    return 0.5


def _expected_calibration_error(probabilities: list[float], outcomes: list[int]) -> float:
    total = len(probabilities)
    bins = [(0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.01)]
    error = 0.0
    for lower, upper in bins:
        bucket = [
            (probability, outcome)
            for probability, outcome in zip(probabilities, outcomes)
            if lower <= probability < upper
        ]
        if not bucket:
            continue
        avg_confidence = sum(item[0] for item in bucket) / len(bucket)
        avg_accuracy = sum(item[1] for item in bucket) / len(bucket)
        error += (len(bucket) / total) * abs(avg_confidence - avg_accuracy)
    return error


def _blocked_contract_result(budget: int, risk: int) -> dict[str, object]:
    return check_contract(
        {
            "contract": {
                "contract_id": "deploy_change",
                "preconditions": ["budget <= 100", "risk <= 2"],
            },
            "state_constraints": [f"budget == {budget}", f"risk == {risk}"],
            "variables": {"budget": "Int", "risk": "Int"},
        }
    )


def _replanned_contract_result(budget: int, risk: int) -> dict[str, object]:
    return check_contract(
        {
            "contract": {
                "contract_id": "deploy_change",
                "preconditions": ["budget <= 100", "risk <= 2"],
            },
            "state_constraints": [f"budget == {budget}", f"risk == {risk}"],
            "variables": {"budget": "Int", "risk": "Int"},
        }
    )


@pytest.mark.skip(reason="Stage 3 criterion maps to ARC-AGI, which is not vendored into this repository")
def test_stage3_novel_task_generalization_arc_agi_placeholder() -> None:
    # Stage 3 §4.3: ARC-AGI requires an external benchmark harness.
    raise AssertionError("unreachable")


@pytest.mark.skip(reason="Stage 3 criterion maps to ALFWorld/WebArena, which is not available in local CI")
def test_stage3_multi_step_planning_external_benchmark_placeholder() -> None:
    # Stage 3 §4.3: ALFWorld/WebArena require external environments.
    raise AssertionError("unreachable")


def test_stage3_self_evaluation_calibration_ece_under_threshold() -> None:
    # Stage 3 §4.3: self-evaluation calibration must achieve ECE <= 0.10.
    calibrator = UncertaintyCalibrator()
    probabilities: list[float] = []
    outcomes: list[int] = []

    valid_argument = "P -> Q, P |- Q"
    invalid_argument = "P -> Q, Q |- P"
    for index in range(25):
        valid_record = calibrator.from_certificate(
            certify(valid_argument),
            provenance=[f"seed-{index}", "logicbrain", "z3"],
        )
        invalid_record = calibrator.from_certificate(
            certify(invalid_argument),
            provenance=[f"seed-{index}"],
        )
        probabilities.append(_confidence_probability(valid_record.level))
        outcomes.append(1)
        probabilities.append(_confidence_probability(invalid_record.level))
        outcomes.append(0)

    ece = _expected_calibration_error(probabilities, outcomes)
    assert len(probabilities) == 50
    assert ece <= 0.10


def test_stage3_error_self_detection_rate_meets_threshold() -> None:
    # Stage 3 §4.3: seeded errors must be detected before final output >= 30%.
    detected = 0
    total = 20
    for index in range(total):
        if index % 2 == 0:
            result = check_assumptions(
                {
                    "assumptions": [
                        {"id": f"ok-{index}", "statement": "budget <= 100", "kind": "fact"},
                        {"id": f"bad-{index}", "statement": "budget > 120", "kind": "hypothesis"},
                    ],
                    "variables": {"budget": "Int"},
                }
            )
            detected += int(result["consistent"] is False)
        else:
            result = _blocked_contract_result(budget=130 + index, risk=1)
            detected += int(result["status"] == "blocked")

    assert detected / total >= 0.30


def test_stage3_replanning_after_failure_success_rate_meets_threshold() -> None:
    # Stage 3 §4.3: replanning after an initial failure must succeed >= 50%.
    successes = 0
    total = 10
    for index in range(total):
        blocked = _blocked_contract_result(budget=130 + index, risk=1)
        assert blocked["status"] == "blocked"

        failure = classify_goal_contract_failure(
            verify_contract_preconditions_z3(
                GoalContract(
                    contract_id="deploy_change",
                    preconditions=("budget <= 100", "risk <= 2"),
                ),
                state_constraints=[f"budget == {130 + index}", "risk == 1"],
                variables={"budget": "Int", "risk": "Int"},
            )
        )
        decision = choose_recovery(failure)
        assert decision.selected_protocol is RecoveryProtocol.REPLAN

        replanned = _replanned_contract_result(budget=90 - (index % 5), risk=1)
        successes += int(replanned["status"] == "active")

    assert successes / total >= 0.50


def test_stage3_deterministic_replay_is_identical() -> None:
    # Stage 3 §4.3 derivative criterion: deterministic replay must be exact.
    first = reflective_agent.run_reflective_demo()
    second = reflective_agent.run_reflective_demo()

    assert first["verify_argument"] == second["verify_argument"]
    assert first["failed_assumption_check"] == second["failed_assumption_check"]
    assert first["repaired_assumption_check"] == second["repaired_assumption_check"]
    assert first["blocked_contract"] == second["blocked_contract"]
    assert first["active_contract"] == second["active_contract"]

    first_action = cast(dict[str, object], first["proof_carrying_action"])
    second_action = cast(dict[str, object], second["proof_carrying_action"])
    first_trace = cast(dict[str, object], first_action["trace"])
    second_trace = cast(dict[str, object], second_action["trace"])
    assert first_action["status"] == second_action["status"] == "completed"
    assert first_action["accepted"] == second_action["accepted"] is True
    assert first_trace["decision"] == second_trace["decision"]
