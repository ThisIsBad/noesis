"""Metamorphic tests for Z3Session relational invariants (Issue #28)."""

from __future__ import annotations

import pytest

from logos.z3_session import Z3Session


pytestmark = pytest.mark.metamorphic


def _run_int_session(constraints: list[str]) -> tuple[str, bool | None]:
    session = Z3Session()
    session.declare("x", "Int")
    session.declare("y", "Int")
    for c in constraints:
        session.assert_constraint(c)
    result = session.check()
    return result.status, result.satisfiable


def test_mr_push_pop_restores_baseline_sat() -> None:
    session = Z3Session()
    session.declare("x", "Int")
    session.assert_constraint("x > 0")

    baseline = session.check()
    assert baseline.status == "sat"

    session.push()
    session.assert_constraint("x < 0")  # contradiction in pushed scope
    pushed = session.check()
    assert pushed.status == "unsat"

    session.pop()
    restored = session.check()
    assert restored.status == baseline.status
    assert restored.satisfiable == baseline.satisfiable


def test_mr_reordering_independent_constraints_preserves_sat() -> None:
    a = ["x > 0", "y > x", "x + y < 20"]
    b = ["x + y < 20", "y > x", "x > 0"]

    status_a, sat_a = _run_int_session(a)
    status_b, sat_b = _run_int_session(b)

    assert (status_a, sat_a) == (status_b, sat_b)


def test_mr_reordering_contradictory_constraints_preserves_unsat() -> None:
    a = ["x > 0", "x < 0", "y == 1"]
    b = ["y == 1", "x < 0", "x > 0"]

    status_a, sat_a = _run_int_session(a)
    status_b, sat_b = _run_int_session(b)

    assert (status_a, sat_a) == (status_b, sat_b) == ("unsat", False)


def test_mr_equivalent_integer_bounds_preserve_classification() -> None:
    # For Ints, x > 5 is equivalent to x >= 6.
    status_a, sat_a = _run_int_session(["x > 5", "x < 10"])
    status_b, sat_b = _run_int_session(["x >= 6", "x < 10"])

    assert (status_a, sat_a) == (status_b, sat_b)


def test_mr_reset_clears_state_and_redeclaration_behaves_like_fresh_session() -> None:
    used = Z3Session()
    used.declare("x", "Int")
    used.assert_constraint("x > 0")
    used.reset()
    used.declare("x", "Int")
    used.assert_constraint("x == 3")
    result_used = used.check()

    fresh = Z3Session()
    fresh.declare("x", "Int")
    fresh.assert_constraint("x == 3")
    result_fresh = fresh.check()

    assert result_used.status == result_fresh.status == "sat"
    assert result_used.satisfiable is True and result_fresh.satisfiable is True


def test_mr_unsat_core_tracking_preserves_unsat_relation_across_ordering() -> None:
    s1 = Z3Session(track_unsat_core=True)
    s1.declare("x", "Int")
    s1.assert_constraint("x > 0", name="positive")
    s1.assert_constraint("x < 0", name="negative")
    r1 = s1.check()

    s2 = Z3Session(track_unsat_core=True)
    s2.declare("x", "Int")
    s2.assert_constraint("x < 0", name="negative")
    s2.assert_constraint("x > 0", name="positive")
    r2 = s2.check()

    assert r1.status == r2.status == "unsat"
    assert r1.unsat_core is not None and r2.unsat_core is not None
    assert isinstance(r1.unsat_core, list)
    assert isinstance(r2.unsat_core, list)
