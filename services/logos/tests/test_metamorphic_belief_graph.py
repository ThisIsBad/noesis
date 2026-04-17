"""Metamorphic tests for causal/temporal belief graph (Issue #46)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from logos import BeliefEdgeType, BeliefGraph


pytestmark = pytest.mark.metamorphic


def test_mr_bg01_support_order_invariance() -> None:
    ordered = BeliefGraph()
    ordered.add_belief("a", "Root")
    ordered.add_belief("b", "Mid")
    ordered.add_belief("c", "Goal")
    ordered.add_edge("a", "b", BeliefEdgeType.SUPPORTS)
    ordered.add_edge("b", "c", BeliefEdgeType.DERIVED_FROM)

    reordered = BeliefGraph()
    reordered.add_belief("a", "Root")
    reordered.add_belief("b", "Mid")
    reordered.add_belief("c", "Goal")
    reordered.add_edge("b", "c", BeliefEdgeType.DERIVED_FROM)
    reordered.add_edge("a", "b", BeliefEdgeType.SUPPORTS)

    assert ordered.minimal_support_set("c") == reordered.minimal_support_set("c")


def test_mr_bg02_temporal_shift_consistency() -> None:
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    shift = timedelta(hours=3)

    graph_a = BeliefGraph()
    graph_a.add_belief("a", "Evidence", valid_from=base_time, ttl_seconds=60)
    graph_a.add_belief("b", "Claim", valid_from=base_time)
    graph_a.add_edge("a", "b", BeliefEdgeType.SUPPORTS)
    stale_a = graph_a.stale_dependencies(at_time=base_time + timedelta(minutes=5))

    graph_b = BeliefGraph()
    graph_b.add_belief("a", "Evidence", valid_from=base_time + shift, ttl_seconds=60)
    graph_b.add_belief("b", "Claim", valid_from=base_time + shift)
    graph_b.add_edge("a", "b", BeliefEdgeType.SUPPORTS)
    stale_b = graph_b.stale_dependencies(at_time=base_time + shift + timedelta(minutes=5))

    assert stale_a == stale_b


def test_mr_bg03_adding_equivalent_belief_does_not_change_contradiction_verdict() -> None:
    baseline = BeliefGraph()
    baseline.add_belief("a", "x > 0")
    baseline.add_belief("b", "x < 0")

    augmented = BeliefGraph()
    augmented.add_belief("a", "x > 0")
    augmented.add_belief("b", "x < 0")
    augmented.add_belief("tautology", "x == x")

    baseline_result = baseline.detect_contradictions_z3(variables={"x": "Int"})
    augmented_result = augmented.detect_contradictions_z3(variables={"x": "Int"})

    assert baseline_result == augmented_result
    assert baseline_result.status is augmented_result.status


def test_mr_bg04_contradiction_verdict_is_invariant_to_belief_add_order() -> None:
    ordered = BeliefGraph()
    ordered.add_belief("left", "x > 0")
    ordered.add_belief("right", "x < 0")
    ordered.add_belief("context", "x < 10")

    reordered = BeliefGraph()
    reordered.add_belief("context", "x < 10")
    reordered.add_belief("right", "x < 0")
    reordered.add_belief("left", "x > 0")

    ordered_result = ordered.detect_contradictions_z3(variables={"x": "Int"})
    reordered_result = reordered.detect_contradictions_z3(variables={"x": "Int"})

    assert ordered_result == reordered_result
    assert ordered_result.status is reordered_result.status


def test_mr_bg05_removing_any_witness_belief_resolves_contradiction() -> None:
    graph = BeliefGraph()
    graph.add_belief("left-root", "x > 0")
    graph.add_belief("left", "x > -5")
    graph.add_belief("right-root", "x < 0")
    graph.add_belief("right", "x < 5")
    graph.add_edge("left-root", "left", BeliefEdgeType.SUPPORTS)
    graph.add_edge("right-root", "right", BeliefEdgeType.SUPPORTS)

    graph.detect_contradictions_z3(variables={"x": "Int"})
    witness = graph.explain_contradiction("left", "right").witness_ids

    for removed in witness:
        candidate = BeliefGraph()
        if removed != "left-root":
            candidate.add_belief("left-root", "x > 0")
        candidate.add_belief("left", "x > -5")
        if removed != "right-root":
            candidate.add_belief("right-root", "x < 0")
        candidate.add_belief("right", "x < 5")
        if removed != "left-root":
            candidate.add_edge("left-root", "left", BeliefEdgeType.SUPPORTS)
        if removed != "right-root":
            candidate.add_edge("right-root", "right", BeliefEdgeType.SUPPORTS)

        result = candidate.detect_contradictions_z3(variables={"x": "Int"})
        assert result == ()
