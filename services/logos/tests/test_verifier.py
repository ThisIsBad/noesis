"""Tests for the deterministic verifier — the verifier MUST be correct.

If the verifier has bugs, the entire framework is worthless.
These tests validate every supported inference rule and known fallacy.
"""

import pytest

from logos.models import (
    Argument,
    Connective,
    LogicalExpression,
    Proposition,
)
from logos.verifier import PropositionalVerifier


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def v():
    return PropositionalVerifier()


@pytest.fixture
def P():
    return Proposition("P")


@pytest.fixture
def Q():
    return Proposition("Q")


@pytest.fixture
def R():
    return Proposition("R")


@pytest.fixture
def S():
    return Proposition("S")


# ---------------------------------------------------------------------------
# VALID inference rules
# ---------------------------------------------------------------------------


class TestValidInferences:
    """The verifier must recognise all valid inference rules."""

    def test_modus_ponens(self, v, P, Q):
        """P → Q, P ⊢ Q"""
        arg = Argument(
            premises=[LogicalExpression(Connective.IMPLIES, P, Q), P],
            conclusion=Q,
        )
        result = v.verify(arg)
        assert result.valid is True
        assert result.counterexample is None

    def test_modus_tollens(self, v, P, Q):
        """P → Q, ¬Q ⊢ ¬P"""
        arg = Argument(
            premises=[
                LogicalExpression(Connective.IMPLIES, P, Q),
                LogicalExpression(Connective.NOT, Q),
            ],
            conclusion=LogicalExpression(Connective.NOT, P),
        )
        result = v.verify(arg)
        assert result.valid is True

    def test_hypothetical_syllogism(self, v, P, Q, R):
        """P → Q, Q → R ⊢ P → R"""
        arg = Argument(
            premises=[
                LogicalExpression(Connective.IMPLIES, P, Q),
                LogicalExpression(Connective.IMPLIES, Q, R),
            ],
            conclusion=LogicalExpression(Connective.IMPLIES, P, R),
        )
        result = v.verify(arg)
        assert result.valid is True

    def test_disjunctive_syllogism(self, v, P, Q):
        """P ∨ Q, ¬P ⊢ Q"""
        arg = Argument(
            premises=[
                LogicalExpression(Connective.OR, P, Q),
                LogicalExpression(Connective.NOT, P),
            ],
            conclusion=Q,
        )
        result = v.verify(arg)
        assert result.valid is True

    def test_conjunction_introduction(self, v, P, Q):
        """P, Q ⊢ P ∧ Q"""
        arg = Argument(
            premises=[P, Q],
            conclusion=LogicalExpression(Connective.AND, P, Q),
        )
        result = v.verify(arg)
        assert result.valid is True

    def test_conjunction_elimination(self, v, P, Q):
        """P ∧ Q ⊢ P"""
        arg = Argument(
            premises=[LogicalExpression(Connective.AND, P, Q)],
            conclusion=P,
        )
        result = v.verify(arg)
        assert result.valid is True

    def test_disjunction_introduction(self, v, P, Q):
        """P ⊢ P ∨ Q"""
        arg = Argument(
            premises=[P],
            conclusion=LogicalExpression(Connective.OR, P, Q),
        )
        result = v.verify(arg)
        assert result.valid is True

    def test_contraposition(self, v, P, Q):
        """P → Q ⊢ ¬Q → ¬P"""
        arg = Argument(
            premises=[LogicalExpression(Connective.IMPLIES, P, Q)],
            conclusion=LogicalExpression(
                Connective.IMPLIES,
                LogicalExpression(Connective.NOT, Q),
                LogicalExpression(Connective.NOT, P),
            ),
        )
        result = v.verify(arg)
        assert result.valid is True

    def test_double_negation(self, v, P):
        """¬¬P ⊢ P"""
        arg = Argument(
            premises=[LogicalExpression(Connective.NOT, LogicalExpression(Connective.NOT, P))],
            conclusion=P,
        )
        result = v.verify(arg)
        assert result.valid is True

    def test_de_morgan_and(self, v, P, Q):
        """¬(P ∧ Q) ⊢ ¬P ∨ ¬Q"""
        arg = Argument(
            premises=[LogicalExpression(Connective.NOT, LogicalExpression(Connective.AND, P, Q))],
            conclusion=LogicalExpression(
                Connective.OR,
                LogicalExpression(Connective.NOT, P),
                LogicalExpression(Connective.NOT, Q),
            ),
        )
        result = v.verify(arg)
        assert result.valid is True

    def test_de_morgan_or(self, v, P, Q):
        """¬(P ∨ Q) ⊢ ¬P ∧ ¬Q"""
        arg = Argument(
            premises=[LogicalExpression(Connective.NOT, LogicalExpression(Connective.OR, P, Q))],
            conclusion=LogicalExpression(
                Connective.AND,
                LogicalExpression(Connective.NOT, P),
                LogicalExpression(Connective.NOT, Q),
            ),
        )
        result = v.verify(arg)
        assert result.valid is True

    def test_reductio_ad_absurdum(self, v, P, Q):
        """P → Q, P → ¬Q ⊢ ¬P"""
        arg = Argument(
            premises=[
                LogicalExpression(Connective.IMPLIES, P, Q),
                LogicalExpression(Connective.IMPLIES, P, LogicalExpression(Connective.NOT, Q)),
            ],
            conclusion=LogicalExpression(Connective.NOT, P),
        )
        result = v.verify(arg)
        assert result.valid is True

    def test_constructive_dilemma(self, v, P, Q, R, S):
        """(P→Q), (R→S), (P∨R) ⊢ (Q∨S)"""
        arg = Argument(
            premises=[
                LogicalExpression(Connective.IMPLIES, P, Q),
                LogicalExpression(Connective.IMPLIES, R, S),
                LogicalExpression(Connective.OR, P, R),
            ],
            conclusion=LogicalExpression(Connective.OR, Q, S),
        )
        result = v.verify(arg)
        assert result.valid is True


# ---------------------------------------------------------------------------
# INVALID arguments (fallacies)
# ---------------------------------------------------------------------------


class TestInvalidArguments:
    """The verifier must correctly reject fallacies and provide counterexamples."""

    def test_affirming_consequent(self, v, P, Q):
        """P → Q, Q ⊬ P"""
        arg = Argument(
            premises=[LogicalExpression(Connective.IMPLIES, P, Q), Q],
            conclusion=P,
        )
        result = v.verify(arg)
        assert result.valid is False
        assert result.counterexample is not None
        # In the counterexample: P must be False, Q must be True
        assert result.counterexample["P"] is False
        assert result.counterexample["Q"] is True

    def test_denying_antecedent(self, v, P, Q):
        """P → Q, ¬P ⊬ ¬Q"""
        arg = Argument(
            premises=[
                LogicalExpression(Connective.IMPLIES, P, Q),
                LogicalExpression(Connective.NOT, P),
            ],
            conclusion=LogicalExpression(Connective.NOT, Q),
        )
        result = v.verify(arg)
        assert result.valid is False
        assert result.counterexample is not None

    def test_invalid_chain(self, v):
        """A→B, C→B, A ⊬ C"""
        A, B, C = Proposition("A"), Proposition("B"), Proposition("C")
        arg = Argument(
            premises=[
                LogicalExpression(Connective.IMPLIES, A, B),
                LogicalExpression(Connective.IMPLIES, C, B),
                A,
            ],
            conclusion=C,
        )
        result = v.verify(arg)
        assert result.valid is False

    def test_converse_error(self, v):
        """D→M, M ⊬ D (All dogs are mammals, Rex is a mammal ⊬ Rex is a dog)"""
        D, M = Proposition("D"), Proposition("M")
        arg = Argument(
            premises=[LogicalExpression(Connective.IMPLIES, D, M), M],
            conclusion=D,
        )
        result = v.verify(arg)
        assert result.valid is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and special forms."""

    def test_tautology(self, v, P):
        """P ∨ ¬P is a tautology."""
        expr = LogicalExpression(Connective.OR, P, LogicalExpression(Connective.NOT, P))
        result = v.is_tautology(expr)
        assert result.valid is True

    def test_contradiction(self, v, P):
        """P ∧ ¬P is a contradiction."""
        expr = LogicalExpression(Connective.AND, P, LogicalExpression(Connective.NOT, P))
        result = v.is_contradiction(expr)
        assert result.valid is True

    def test_equivalence_de_morgan(self, v, P, Q):
        """¬(P ∧ Q) ≡ ¬P ∨ ¬Q"""
        a = LogicalExpression(Connective.NOT, LogicalExpression(Connective.AND, P, Q))
        b = LogicalExpression(
            Connective.OR,
            LogicalExpression(Connective.NOT, P),
            LogicalExpression(Connective.NOT, Q),
        )
        result = v.check_equivalence(a, b)
        assert result.valid is True

    def test_non_equivalence(self, v, P, Q):
        """P → Q is NOT equivalent to Q → P."""
        a = LogicalExpression(Connective.IMPLIES, P, Q)
        b = LogicalExpression(Connective.IMPLIES, Q, P)
        result = v.check_equivalence(a, b)
        assert result.valid is False

    def test_empty_premises_atom(self, v, P):
        """No premises, conclusion P → NOT valid (P is not a tautology)."""
        arg = Argument(premises=[], conclusion=P)
        result = v.verify(arg)
        assert result.valid is False

    def test_single_premise_identity(self, v, P):
        """P ⊢ P is trivially valid."""
        arg = Argument(premises=[P], conclusion=P)
        result = v.verify(arg)
        assert result.valid is True


# ---------------------------------------------------------------------------
# Benchmark suite correctness
# ---------------------------------------------------------------------------


class TestBenchmarkSuite:
    """Verify that the verifier agrees with every expected_valid flag."""

    def test_all_benchmarks_match(self):
        from logos.runner import BenchmarkRunner

        runner = BenchmarkRunner()
        results = runner.run_all()

        mismatches = [r for r in results if not r.verifier_correct]
        if mismatches:
            details = "\n".join(
                f"  {r.problem_id}: expected={'valid' if r.expected_valid else 'invalid'}, "
                f"got={'valid' if r.actual_valid else 'invalid'}"
                for r in mismatches
            )
            pytest.fail(f"Verifier mismatches:\n{details}")
