"""Tests for structured diagnostics parsing and formatting."""

from logos.diagnostics import (
    Diagnostic,
    ErrorType,
    LeanDiagnosticParser,
    Z3DiagnosticParser,
)


def test_diagnostic_string_includes_expected_sections():
    diagnostic = Diagnostic(
        error_type=ErrorType.TYPE_MISMATCH,
        message="type mismatch",
        expected="Nat",
        actual="Bool",
        suggestions=["Try coercion"],
    )

    text = str(diagnostic)

    assert "[type_mismatch]" in text
    assert "Expected: Nat" in text
    assert "Actual:   Bool" in text
    assert "Try coercion" in text


def test_lean_parser_identifies_unknown_tactic_and_suggestion():
    output = "tmp.lean:3:2: error: unknown tactic 'reflexivity'"

    diagnostic = LeanDiagnosticParser.parse(output, tactic="reflexivity")

    assert diagnostic.error_type == ErrorType.UNKNOWN_TACTIC
    assert any("Did you mean: rfl" in s for s in diagnostic.suggestions)


def test_lean_parser_extracts_type_mismatch_types():
    output = (
        "tmp.lean:4:10: error: type mismatch\n"
        "term has type Bool but is expected to have type Nat"
    )

    diagnostic = LeanDiagnosticParser.parse(output, tactic="exact")

    assert diagnostic.error_type == ErrorType.TYPE_MISMATCH
    assert diagnostic.expected == "Nat"
    assert diagnostic.actual == "Bool"


def test_z3_unsat_parser_with_unsat_core():
    diagnostic = Z3DiagnosticParser.parse_unsat(
        constraints=["x > 0", "x < 0"],
        unsat_core=["positive", "negative"],
    )

    assert diagnostic.error_type == ErrorType.UNSATISFIABLE
    assert "unsatisfiable" in diagnostic.message.lower()
    assert any("positive" in s and "negative" in s for s in diagnostic.suggestions)


def test_z3_constraint_error_parser_undeclared_variable():
    diagnostic = Z3DiagnosticParser.parse_constraint_error(
        "name 'y' is not defined",
        "y > 0",
    )

    assert diagnostic.error_type == ErrorType.UNDECLARED_VARIABLE
    assert "variable" in diagnostic.message.lower()
    assert diagnostic.actual == "y > 0"
