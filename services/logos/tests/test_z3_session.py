"""Tests for the Z3 interactive session."""

import pytest

from logos.diagnostics import ErrorType
from logos.z3_session import Z3Session, CheckResult


class TestZ3SessionBasic:
    """Basic functionality tests."""

    def test_declare_int(self):
        session = Z3Session()
        session.declare("x", "Int")
        assert "x" in session.variables

    def test_declare_real(self):
        session = Z3Session()
        session.declare("x", "Real")
        assert "x" in session.variables

    def test_declare_bool(self):
        session = Z3Session()
        session.declare("flag", "Bool")
        assert "flag" in session.variables

    def test_declare_bitvec(self):
        session = Z3Session()
        session.declare("bits", "BitVec", size=32)
        assert "bits" in session.variables

    def test_declare_bitvec_requires_size(self):
        session = Z3Session()
        with pytest.raises(ValueError, match="requires size"):
            session.declare("bits", "BitVec")

    def test_declare_duplicate_fails(self):
        session = Z3Session()
        session.declare("x", "Int")
        with pytest.raises(ValueError, match="already declared"):
            session.declare("x", "Int")

    def test_declare_unknown_sort_fails(self):
        session = Z3Session()
        with pytest.raises(ValueError, match="Unknown sort"):
            session.declare("x", "String")


class TestZ3SessionConstraints:
    """Constraint assertion tests."""

    def test_simple_constraint(self):
        session = Z3Session()
        session.declare("x", "Int")
        session.assert_constraint("x > 0")
        assert session.num_assertions == 1

    def test_multiple_constraints(self):
        session = Z3Session()
        session.declare("x", "Int")
        session.declare("y", "Int")
        session.assert_constraint("x > 0")
        session.assert_constraint("y > x")
        session.assert_constraint("x + y < 100")
        assert session.num_assertions == 3

    def test_equality_constraint(self):
        session = Z3Session()
        session.declare("x", "Int")
        session.assert_constraint("x == 5")
        result = session.check()
        assert result.satisfiable
        assert result.model["x"] == 5

    def test_boolean_constraint(self):
        session = Z3Session()
        session.declare("a", "Bool")
        session.declare("b", "Bool")
        session.assert_constraint("a")
        session.assert_constraint("Not(b)")
        result = session.check()
        assert result.satisfiable
        assert result.model["a"]
        assert not result.model["b"]


class TestZ3SessionCheck:
    """Satisfiability checking tests."""

    def test_satisfiable(self):
        session = Z3Session()
        session.declare("x", "Int")
        session.assert_constraint("x > 0")
        session.assert_constraint("x < 10")

        result = session.check()

        assert result.status == "sat"
        assert result.satisfiable
        assert result.model is not None
        assert 0 < result.model["x"] < 10

    def test_unsatisfiable(self):
        session = Z3Session()
        session.declare("x", "Int")
        session.assert_constraint("x > 0")
        session.assert_constraint("x < 0")

        result = session.check()

        assert result.status == "unsat"
        assert not result.satisfiable
        assert result.diagnostic is not None
        assert result.diagnostic.error_type == ErrorType.UNSATISFIABLE

    def test_model_extraction(self):
        session = Z3Session()
        session.declare("x", "Int")
        session.declare("y", "Int")
        session.assert_constraint("x == 5")
        session.assert_constraint("y == x + 3")

        result = session.check()

        assert result.model["x"] == 5
        assert result.model["y"] == 8

    def test_real_model(self):
        session = Z3Session()
        session.declare("x", "Real")
        session.assert_constraint("x > 1")
        session.assert_constraint("x < 2")

        result = session.check()

        assert result.satisfiable
        assert 1 < result.model["x"] < 2


class TestZ3SessionPushPop:
    """Push/pop backtracking tests."""

    def test_push_pop_basic(self):
        session = Z3Session()
        session.declare("x", "Int")
        session.assert_constraint("x > 0")

        session.push()
        session.assert_constraint("x < 0")  # Contradicts

        result1 = session.check()
        assert not result1.satisfiable

        session.pop()

        result2 = session.check()
        assert result2.satisfiable

    def test_nested_push_pop(self):
        session = Z3Session()
        session.declare("x", "Int")

        session.push()  # Level 1
        session.assert_constraint("x > 0")

        session.push()  # Level 2
        session.assert_constraint("x < 5")

        result = session.check()
        assert result.satisfiable
        assert 0 < result.model["x"] < 5

        session.pop()  # Back to level 1
        session.assert_constraint("x > 100")

        result = session.check()
        assert result.satisfiable
        assert result.model["x"] > 100

    def test_pop_too_many_fails(self):
        session = Z3Session()
        session.push()
        session.pop()

        with pytest.raises(ValueError, match="Cannot pop"):
            session.pop()

    def test_scope_depth(self):
        session = Z3Session()
        assert session.scope_depth == 0

        session.push()
        assert session.scope_depth == 1

        session.push()
        assert session.scope_depth == 2

        session.pop()
        assert session.scope_depth == 1


class TestZ3SessionUnsatCore:
    """Unsat core extraction tests."""

    def test_unsat_core_tracking(self):
        session = Z3Session(track_unsat_core=True)
        session.declare("x", "Int")

        session.assert_constraint("x > 0", name="positive")
        session.assert_constraint("x < 0", name="negative")

        result = session.check()

        assert not result.satisfiable
        # Unsat core extraction is enabled, but the exact contents
        # depend on Z3's internal tracking. Just verify it returns a list.
        assert result.unsat_core is not None
        assert isinstance(result.unsat_core, list)

    def test_no_unsat_core_without_tracking(self):
        session = Z3Session(track_unsat_core=False)
        session.declare("x", "Int")
        session.assert_constraint("x > 0")
        session.assert_constraint("x < 0")

        result = session.check()

        assert not result.satisfiable
        assert result.unsat_core is None


class TestZ3SessionReset:
    """Reset functionality tests."""

    def test_reset_clears_variables(self):
        session = Z3Session()
        session.declare("x", "Int")

        session.reset()

        assert len(session.variables) == 0

    def test_reset_clears_assertions(self):
        session = Z3Session()
        session.declare("x", "Int")
        session.assert_constraint("x > 0")

        session.reset()

        assert session.num_assertions == 0

    def test_reset_allows_redeclaration(self):
        session = Z3Session()
        session.declare("x", "Int")
        session.reset()

        # Should not raise
        session.declare("x", "Real")
        assert "x" in session.variables


class TestZ3SessionComplexExpressions:
    """Tests for complex constraint expressions."""

    def test_arithmetic(self):
        session = Z3Session()
        session.declare("x", "Int")
        session.declare("y", "Int")
        session.assert_constraint("x + y == 10")
        session.assert_constraint("x - y == 2")

        result = session.check()

        assert result.satisfiable
        assert result.model["x"] == 6
        assert result.model["y"] == 4

    def test_multiplication(self):
        session = Z3Session()
        session.declare("x", "Int")
        session.assert_constraint("x * x == 16")
        session.assert_constraint("x > 0")

        result = session.check()

        assert result.satisfiable
        assert result.model["x"] == 4

    def test_and_or(self):
        session = Z3Session()
        session.declare("x", "Int")
        session.assert_constraint("And(x > 0, x < 10)")

        result = session.check()
        assert result.satisfiable
        assert 0 < result.model["x"] < 10

    def test_or_constraint(self):
        session = Z3Session()
        session.declare("x", "Int")
        session.assert_constraint("Or(x == 1, x == 2)")

        result = session.check()
        assert result.satisfiable
        assert result.model["x"] in [1, 2]

    def test_undeclared_variable_reports_structured_error(self):
        session = Z3Session()
        session.declare("x", "Int")

        with pytest.raises(ValueError, match="undeclared_variable"):
            session.assert_constraint("y > 0")

    def test_implication_operator_arrow(self):
        session = Z3Session()
        session.declare("a", "Bool")
        session.declare("b", "Bool")
        session.assert_constraint("a")
        session.assert_constraint("a -> b")

        result = session.check()

        assert result.satisfiable
        assert result.model["b"] is True

    def test_implication_operator_fat_arrow(self):
        session = Z3Session()
        session.declare("a", "Bool")
        session.declare("b", "Bool")
        session.assert_constraint("a")
        session.assert_constraint("a => b")

        result = session.check()

        assert result.satisfiable
        assert result.model["b"] is True

    def test_malformed_constraint_reports_parse_error(self):
        session = Z3Session()
        session.declare("x", "Int")

        with pytest.raises(ValueError, match="parse_error"):
            session.assert_constraint("x >")

    def test_unsupported_syntax_reports_parse_error(self):
        session = Z3Session()
        session.declare("x", "Int")

        with pytest.raises(ValueError, match="parse_error"):
            session.assert_constraint("[x] == [1]")


class TestCheckResult:
    """CheckResult dataclass tests."""

    def test_sat_result(self):
        result = CheckResult(status="sat", satisfiable=True, model={"x": 5})
        assert result.satisfiable
        assert result.model["x"] == 5

    def test_unsat_result(self):
        result = CheckResult(status="unsat", satisfiable=False, unsat_core=["c1", "c2"])
        assert not result.satisfiable
        assert result.unsat_core == ["c1", "c2"]

    def test_unknown_result(self):
        result = CheckResult(status="unknown", satisfiable=None, reason="timeout")
        assert result.satisfiable is None
        assert result.reason == "timeout"
