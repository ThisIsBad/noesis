"""Tests for causal and temporal belief graph (Issue #46)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from logos import AssumptionKind, AssumptionSet, BeliefEdgeType, BeliefGraph, UncertaintyCalibrator
from logos.belief_graph import ContradictionStatus
from logos.z3_session import CheckResult
from logos.uncertainty import ConfidenceLevel


def test_minimal_support_set_traces_to_root_supports() -> None:
    graph = BeliefGraph()
    graph.add_belief("a", "Root fact")
    graph.add_belief("b", "Intermediate")
    graph.add_belief("c", "Conclusion")
    graph.add_edge("a", "b", BeliefEdgeType.SUPPORTS)
    graph.add_edge("b", "c", BeliefEdgeType.DERIVED_FROM)

    assert graph.minimal_support_set("c") == ("a",)


def test_stale_dependencies_are_detected_deterministically() -> None:
    graph = BeliefGraph()
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    graph.add_belief("a", "Old evidence", valid_from=t0, ttl_seconds=60)
    graph.add_belief("b", "Current claim", valid_from=t0)
    graph.add_edge("a", "b", BeliefEdgeType.SUPPORTS)

    stale = graph.stale_dependencies(at_time=t0 + timedelta(seconds=120))
    assert stale == ("a",)


def test_contradiction_frontier_and_explanation_are_explicit() -> None:
    graph = BeliefGraph()
    graph.add_belief("r1", "Base support left")
    graph.add_belief("r2", "Base support right")
    graph.add_belief("left", "P")
    graph.add_belief("right", "~P")
    graph.add_edge("r1", "left", BeliefEdgeType.SUPPORTS)
    graph.add_edge("r2", "right", BeliefEdgeType.SUPPORTS)
    graph.add_edge("left", "right", BeliefEdgeType.CONTRADICTS)

    frontier = graph.contradiction_frontier()
    explanation = graph.explain_contradiction("left", "right")

    assert frontier == (("left", "right"),)
    assert explanation.left_support_path == ("left", "r1")
    assert explanation.right_support_path == ("right", "r2")


def test_z3_contradiction_detection_finds_real_contradictions() -> None:
    graph = BeliefGraph()
    graph.add_belief("a", "x > 0")
    graph.add_belief("b", "x < 0")
    graph.add_belief("c", "x < 100")

    contradictions = graph.detect_contradictions_z3(variables={"x": "Int"})

    assert contradictions == (("a", "b"),)
    assert contradictions.status is ContradictionStatus.CONTRADICTION
    assert graph.contradiction_frontier() == (("a", "b"),)

    explanation = graph.explain_contradiction("a", "b")
    assert explanation.witness_ids == ("a", "b")
    assert explanation.status is ContradictionStatus.CONTRADICTION


def test_z3_contradiction_detection_with_no_contradictions() -> None:
    graph = BeliefGraph()
    graph.add_belief("a", "x > 0")
    graph.add_belief("b", "x < 100")

    contradictions = graph.detect_contradictions_z3(variables={"x": "Int"})

    assert contradictions == ()
    assert contradictions.status is ContradictionStatus.CONSISTENT


def test_z3_contradiction_detection_uses_support_closure_for_complex_topology() -> None:
    graph = BeliefGraph()
    graph.add_belief("r1", "x > 0")
    graph.add_belief("r2", "x < 0")
    graph.add_belief("left", "x > -10")
    graph.add_belief("right", "x < 10")
    graph.add_edge("r1", "left", BeliefEdgeType.SUPPORTS)
    graph.add_edge("r2", "right", BeliefEdgeType.SUPPORTS)

    contradictions = graph.detect_contradictions_z3(variables={"x": "Int"})

    assert ("left", "right") in contradictions
    explanation = graph.explain_contradiction("left", "right")
    assert explanation.witness_ids == ("r1", "r2")


def test_z3_contradiction_detection_includes_minimal_witness_for_multi_hop_graph() -> None:
    graph = BeliefGraph()
    graph.add_belief("root-left", "x > 0")
    graph.add_belief("left", "x > -5")
    graph.add_belief("root-right", "x < 0")
    graph.add_belief("right", "x < 5")
    graph.add_belief("extra", "y == 1")
    graph.add_edge("root-left", "left", BeliefEdgeType.SUPPORTS)
    graph.add_edge("root-right", "right", BeliefEdgeType.SUPPORTS)
    graph.add_edge("extra", "right", BeliefEdgeType.SUPPORTS)

    graph.detect_contradictions_z3(variables={"x": "Int", "y": "Int"})

    explanation = graph.explain_contradiction("left", "right")
    assert explanation.witness_ids == ("root-left", "root-right")


def test_z3_contradiction_detection_surfaces_unknown_status(monkeypatch: pytest.MonkeyPatch) -> None:
    graph = BeliefGraph()
    graph.add_belief("a", "x * x == 2")
    graph.add_belief("b", "x * x == 3")

    def fake_check(self: object) -> CheckResult:
        return CheckResult(status="unknown", satisfiable=None, reason="timeout")

    monkeypatch.setattr("logos.z3_session.Z3Session.check", fake_check)

    contradictions = graph.detect_contradictions_z3(variables={"x": "Int"})

    assert contradictions == ()
    assert contradictions.status is ContradictionStatus.UNKNOWN
    assert contradictions.reason == "timeout"


def test_integration_hooks_with_assumptions_and_uncertainty() -> None:
    assumptions = AssumptionSet()
    assumptions.add("a1", "x > 0", AssumptionKind.ASSUMPTION, "sensor")

    graph = BeliefGraph()
    ingested = graph.ingest_assumptions(assumptions)
    level = graph.calibrate_confidence(
        belief_id="a1",
        calibrator=UncertaintyCalibrator(),
        verified=True,
        evidence_count=2,
    )

    assert ingested == ("a1",)
    assert level is ConfidenceLevel.CERTAIN
    assert graph.confidence("a1") is ConfidenceLevel.CERTAIN
