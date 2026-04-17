"""Tests for the string-based logic parser."""

import pytest

from logos.parser import (
    verify,
    parse_argument,
    parse_expression,
    is_tautology,
    is_contradiction,
    are_equivalent,
    ParseError,
)
from logos.models import Proposition, LogicalExpression, Connective


class TestParseExpression:
    """Tests for parsing individual expressions."""

    def test_atom(self):
        expr = parse_expression("P")
        assert isinstance(expr, Proposition)
        assert expr.label == "P"

    def test_negation(self):
        expr = parse_expression("~P")
        assert isinstance(expr, LogicalExpression)
        assert expr.connective == Connective.NOT
        assert isinstance(expr.left, Proposition)
        assert expr.left.label == "P"

    def test_negation_alt(self):
        expr = parse_expression("!P")
        assert isinstance(expr, LogicalExpression)
        assert expr.connective == Connective.NOT

    def test_conjunction(self):
        expr = parse_expression("P & Q")
        assert isinstance(expr, LogicalExpression)
        assert expr.connective == Connective.AND
        assert expr.left == Proposition("P")
        assert expr.right == Proposition("Q")

    def test_conjunction_alt(self):
        expr = parse_expression("P ^ Q")
        assert isinstance(expr, LogicalExpression)
        assert expr.connective == Connective.AND

    def test_disjunction(self):
        expr = parse_expression("P | Q")
        assert isinstance(expr, LogicalExpression)
        assert expr.connective == Connective.OR

    def test_implication(self):
        expr = parse_expression("P -> Q")
        assert isinstance(expr, LogicalExpression)
        assert expr.connective == Connective.IMPLIES

    def test_implication_alt(self):
        expr = parse_expression("P => Q")
        assert isinstance(expr, LogicalExpression)
        assert expr.connective == Connective.IMPLIES

    def test_biconditional(self):
        expr = parse_expression("P <-> Q")
        assert isinstance(expr, LogicalExpression)
        assert expr.connective == Connective.IFF

    def test_biconditional_alt(self):
        expr = parse_expression("P <=> Q")
        assert isinstance(expr, LogicalExpression)
        assert expr.connective == Connective.IFF

    def test_parentheses(self):
        expr = parse_expression("(P -> Q)")
        assert isinstance(expr, LogicalExpression)
        assert expr.connective == Connective.IMPLIES

    def test_complex_expression(self):
        expr = parse_expression("(P -> Q) & (Q -> R)")
        assert isinstance(expr, LogicalExpression)
        assert expr.connective == Connective.AND

    def test_double_negation(self):
        expr = parse_expression("~~P")
        assert isinstance(expr, LogicalExpression)
        assert expr.connective == Connective.NOT
        assert isinstance(expr.left, LogicalExpression)
        assert expr.left.connective == Connective.NOT

    def test_precedence_not_over_and(self):
        # ~P & Q should be (~P) & Q, not ~(P & Q)
        expr = parse_expression("~P & Q")
        assert expr.connective == Connective.AND
        assert isinstance(expr.left, LogicalExpression)
        assert expr.left.connective == Connective.NOT

    def test_precedence_and_over_or(self):
        # P & Q | R should be (P & Q) | R
        expr = parse_expression("P & Q | R")
        assert expr.connective == Connective.OR
        assert isinstance(expr.left, LogicalExpression)
        assert expr.left.connective == Connective.AND

    def test_precedence_or_over_implies(self):
        # P | Q -> R should be (P | Q) -> R
        expr = parse_expression("P | Q -> R")
        assert expr.connective == Connective.IMPLIES
        assert isinstance(expr.left, LogicalExpression)
        assert expr.left.connective == Connective.OR


class TestParseArgument:
    """Tests for parsing full arguments."""

    def test_simple_argument(self):
        arg = parse_argument("P -> Q, P |- Q")
        assert len(arg.premises) == 2
        assert isinstance(arg.conclusion, Proposition)
        assert arg.conclusion.label == "Q"

    def test_single_premise(self):
        arg = parse_argument("P |- P")
        assert len(arg.premises) == 1
        assert arg.conclusion == Proposition("P")

    def test_empty_premises(self):
        arg = parse_argument("|- P | ~P")
        assert len(arg.premises) == 0
        assert isinstance(arg.conclusion, LogicalExpression)

    def test_complex_argument(self):
        arg = parse_argument("P -> Q, Q -> R, P |- R")
        assert len(arg.premises) == 3
        assert arg.conclusion == Proposition("R")

    def test_missing_turnstile(self):
        with pytest.raises(ParseError):
            parse_argument("P -> Q, P")

    def test_empty_input(self):
        with pytest.raises(ParseError):
            parse_argument("")


class TestVerify:
    """Tests for the verify() convenience function."""

    def test_modus_ponens(self):
        result = verify("P -> Q, P |- Q")
        assert result.valid is True
        assert "Modus Ponens" in result.rule

    def test_modus_tollens(self):
        result = verify("P -> Q, ~Q |- ~P")
        assert result.valid is True
        assert "Modus Tollens" in result.rule

    def test_affirming_consequent(self):
        result = verify("P -> Q, Q |- P")
        assert result.valid is False
        assert "fallacy" in result.rule.lower()

    def test_denying_antecedent(self):
        result = verify("P -> Q, ~P |- ~Q")
        assert result.valid is False
        assert "fallacy" in result.rule.lower()

    def test_hypothetical_syllogism(self):
        result = verify("P -> Q, Q -> R |- P -> R")
        assert result.valid is True

    def test_disjunctive_syllogism(self):
        result = verify("P | Q, ~P |- Q")
        assert result.valid is True

    def test_conjunction_introduction(self):
        result = verify("P, Q |- P & Q")
        assert result.valid is True

    def test_conjunction_elimination(self):
        result = verify("P & Q |- P")
        assert result.valid is True

    def test_de_morgan(self):
        result = verify("~(P & Q) |- ~P | ~Q")
        assert result.valid is True

    def test_contraposition(self):
        result = verify("P -> Q |- ~Q -> ~P")
        assert result.valid is True


class TestTautologyAndContradiction:
    """Tests for tautology and contradiction checking."""

    def test_excluded_middle_is_tautology(self):
        result = is_tautology("P | ~P")
        assert result.valid is True

    def test_implication_tautology(self):
        result = is_tautology("P -> P")
        assert result.valid is True

    def test_atom_not_tautology(self):
        result = is_tautology("P")
        assert result.valid is False

    def test_contradiction(self):
        result = is_contradiction("P & ~P")
        assert result.valid is True

    def test_atom_not_contradiction(self):
        result = is_contradiction("P")
        assert result.valid is False


class TestEquivalence:
    """Tests for logical equivalence checking."""

    def test_de_morgan_equivalence(self):
        result = are_equivalent("~(P & Q)", "~P | ~Q")
        assert result.valid is True

    def test_contraposition_equivalence(self):
        result = are_equivalent("P -> Q", "~Q -> ~P")
        assert result.valid is True

    def test_double_negation_equivalence(self):
        result = are_equivalent("~~P", "P")
        assert result.valid is True

    def test_non_equivalence(self):
        result = are_equivalent("P -> Q", "Q -> P")
        assert result.valid is False

    def test_material_implication(self):
        result = are_equivalent("P -> Q", "~P | Q")
        assert result.valid is True


class TestEdgeCases:
    """Edge cases and error handling."""

    def test_whitespace_handling(self):
        result = verify("  P   ->   Q  ,  P   |-   Q  ")
        assert result.valid is True

    def test_invalid_character(self):
        with pytest.raises(ParseError):
            parse_expression("P @ Q")

    def test_unclosed_paren(self):
        with pytest.raises(ParseError):
            parse_expression("(P -> Q")

    def test_extra_tokens(self):
        with pytest.raises(ParseError):
            parse_argument("P |- Q R")

    def test_all_letters(self):
        # Test that all uppercase letters work as atoms
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            expr = parse_expression(letter)
            assert isinstance(expr, Proposition)
            assert expr.label == letter
