"""Metamorphic tests for assumption state kernel (Issue #33)."""

from __future__ import annotations

import pytest

from logos import AssumptionKind, AssumptionSet


pytestmark = pytest.mark.metamorphic


def _build_consistent_set() -> AssumptionSet:
    assumptions = AssumptionSet()
    assumptions.add("a1", "x > 0", AssumptionKind.FACT, "test")
    assumptions.add("a2", "x < 10", AssumptionKind.ASSUMPTION, "test")
    assumptions.add("a3", "y == x + 1", AssumptionKind.HYPOTHESIS, "test")
    return assumptions


def test_mr_a01_z3_redundant_assumption_does_not_change_verdict() -> None:
    baseline = _build_consistent_set()
    redundant = _build_consistent_set()
    redundant.add("a4", "x > 0", AssumptionKind.ASSUMPTION, "test")

    baseline_result = baseline.check_consistency_z3(variables={"x": "Int", "y": "Int"})
    redundant_result = redundant.check_consistency_z3(variables={"x": "Int", "y": "Int"})

    assert baseline_result.consistent is redundant_result.consistent
    assert baseline_result.solver_status == redundant_result.solver_status


def test_mr_a02_z3_verdict_is_invariant_to_insertion_order() -> None:
    ordered = AssumptionSet()
    ordered.add("a1", "x > 0", AssumptionKind.FACT, "test")
    ordered.add("a2", "x < 0", AssumptionKind.HYPOTHESIS, "test")
    ordered.add("a3", "y == x + 1", AssumptionKind.ASSUMPTION, "test")

    reversed_set = AssumptionSet()
    reversed_set.add("a3", "y == x + 1", AssumptionKind.ASSUMPTION, "test")
    reversed_set.add("a2", "x < 0", AssumptionKind.HYPOTHESIS, "test")
    reversed_set.add("a1", "x > 0", AssumptionKind.FACT, "test")

    ordered_result = ordered.check_consistency_z3(variables={"x": "Int", "y": "Int"})
    reversed_result = reversed_set.check_consistency_z3(variables={"x": "Int", "y": "Int"})

    assert ordered_result.consistent is reversed_result.consistent
    assert ordered_result.solver_status == reversed_result.solver_status
