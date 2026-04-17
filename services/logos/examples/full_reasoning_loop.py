"""Full reasoning loop: all LogicBrain modules working together.

This example demonstrates the complete stack from assumptions through
formal verification, showing where Z3 provides real guarantees vs.
where modules are structural only.

Run with:
    python examples/full_reasoning_loop.py
"""

from __future__ import annotations

from logos import (
    AssumptionKind,
    AssumptionSet,
    BeliefGraph,
    CounterfactualPlanner,
    GoalContract,
    GoalContractStatus,
    UncertaintyCalibrator,
    certify,
    evaluate_goal_contract,
    verify_certificate,
    verify_contract_preconditions_z3,
)
from logos.uncertainty import ConfidenceLevel


def main() -> None:
    print("=" * 60)
    print("LogicBrain Full Reasoning Loop")
    print("=" * 60)

    # -- Step 1: Load assumptions --
    print("\n-- Step 1: Assumptions --")
    assumptions = AssumptionSet()
    assumptions.add("budget", "x <= 100", AssumptionKind.FACT, "finance_api")
    assumptions.add("demand", "x > 0", AssumptionKind.ASSUMPTION, "forecast")
    assumptions.add("capacity", "x < 200", AssumptionKind.ASSUMPTION, "ops")

    # Z3-backed consistency check — this is a REAL formal guarantee
    consistency = assumptions.check_consistency_z3(variables={"x": "Int"})
    print(f"  Assumptions consistent (Z3): {consistency.consistent}")
    assert consistency.consistent, "Assumptions must be consistent"

    # Add a contradictory assumption to demonstrate detection
    assumptions.add("impossible", "x > 200", AssumptionKind.HYPOTHESIS, "test")
    contradiction = assumptions.check_consistency_z3(variables={"x": "Int"})
    print(f"  After adding x > 200:  consistent (Z3): {contradiction.consistent}")
    assert not contradiction.consistent, "Should detect contradiction"

    # Retract the bad hypothesis
    assumptions.retract("impossible")
    clean = assumptions.check_consistency_z3(variables={"x": "Int"})
    print(f"  After retraction:      consistent (Z3): {clean.consistent}")

    # -- Step 2: Build belief graph with Z3 contradiction detection --
    print("\n-- Step 2: Belief Graph --")
    graph = BeliefGraph()
    graph.add_belief("b1", "x > 0")
    graph.add_belief("b2", "x < 100")
    graph.add_belief("b3", "x < 0")  # contradicts b1

    # Z3 automatically finds the contradiction
    contradictions = graph.detect_contradictions_z3(variables={"x": "Int"})
    print(f"  Z3-detected contradictions: {contradictions.pairs}")
    assert contradictions == (("b1", "b3"),)

    # -- Step 3: Counterfactual planning --
    print("\n-- Step 3: Counterfactual Planning --")
    planner = CounterfactualPlanner()
    planner.declare("x", "Int")
    planner.assert_constraint("x > 0")
    planner.assert_constraint("x <= 100")

    branch_a = planner.branch("conservative", additional_constraints=["x <= 50"])
    branch_b = planner.branch("aggressive", additional_constraints=["x > 80"])
    branch_c = planner.branch("impossible", additional_constraints=["x > 200"])

    print(f"  conservative: {branch_a.status} (sat={branch_a.satisfiable})")
    print(f"  aggressive:   {branch_b.status} (sat={branch_b.satisfiable})")
    print(f"  impossible:   {branch_c.status} (sat={branch_c.satisfiable})")

    # Certificates are real Z3 proofs
    assert planner.verify_branch_certificate("conservative")
    assert planner.verify_branch_certificate("impossible")
    print("  All branch certificates independently verified.")

    # -- Step 4: Goal contract with Z3-backed preconditions --
    print("\n-- Step 4: Goal Contract --")
    contract = GoalContract(
        contract_id="deploy",
        preconditions=("x > 0", "x <= 100"),
        permitted_strategies=("conservative", "aggressive"),
    )

    # Z3 proves preconditions hold under the state constraints
    state = ["x == 42"]
    z3_result = verify_contract_preconditions_z3(
        contract, state_constraints=state, variables={"x": "Int"}
    )
    print(f"  Z3 precondition check (x=42): {z3_result.status.value}")
    assert z3_result.status is GoalContractStatus.ACTIVE

    # Z3 proves preconditions FAIL under different state
    bad_state = ["x == 150"]
    z3_bad = verify_contract_preconditions_z3(
        contract, state_constraints=bad_state, variables={"x": "Int"}
    )
    print(f"  Z3 precondition check (x=150): {z3_bad.status.value}")
    assert z3_bad.status is GoalContractStatus.BLOCKED

    # Boolean context evaluation still works for quick checks
    bool_result = evaluate_goal_contract(
        contract,
        strategy="conservative",
        context={"sat": True, "unsat": False},
    )
    print(f"  Boolean context check: {bool_result.status.value}")

    # -- Step 5: Uncertainty calibration --
    print("\n-- Step 5: Uncertainty Calibration --")
    calibrator = UncertaintyCalibrator()

    # Certified claim gets high confidence
    cert = certify("P -> Q, P |- Q")
    record = calibrator.from_certificate(
        cert, provenance=["z3_propositional", "policy_check"]
    )
    print(f"  Verified claim confidence: {record.level.value}")
    assert record.level is ConfidenceLevel.CERTAIN

    # Unverified claim gets low confidence
    bad_cert = certify("P -> Q, Q |- P")
    bad_record = calibrator.from_certificate(bad_cert)
    print(f"  Invalid claim confidence:  {bad_record.level.value}")
    assert bad_record.level is ConfidenceLevel.WEAK

    # -- Step 6: Proof certificate for the whole chain --
    print("\n-- Step 6: End-to-End Certificate --")
    final_cert = certify("P -> Q, P |- Q")
    recheck = verify_certificate(final_cert)
    print(f"  Final certificate verified: {recheck}")
    assert recheck

    # -- Summary --
    print("\n" + "=" * 60)
    print("Summary: What was formally verified (Z3-backed)")
    print("=" * 60)
    print("  [Z3] Assumption consistency:    PROVEN")
    print("  [Z3] Belief contradictions:     DETECTED")
    print("  [Z3] Branch sat/unsat:          PROVEN")
    print("  [Z3] Branch certificates:       INDEPENDENTLY VERIFIED")
    print("  [Z3] Goal preconditions:        PROVEN")
    print("  [Z3] Propositional argument:    PROVEN")
    print()
    print("What was structurally checked (not Z3-backed):")
    print("  [BOOL] Boolean context matching")
    print("  [HEUR] Uncertainty classification")
    print("  [DATA] Assumption lifecycle")


if __name__ == "__main__":
    main()
