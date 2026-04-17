"""Direct tests for logos.predicate_models."""

from __future__ import annotations

from logos.predicate_models import (
    Constant,
    FOLArgument,
    Predicate,
    PredicateConnective,
    PredicateExpression,
    QuantifiedExpression,
    Quantifier,
    Variable,
)


def test_predicate_and_terms_string_output():
    x = Variable("x")
    c = Constant("socrates")
    pred = Predicate("Human", (x, c))
    assert str(pred) == "Human(x, socrates)"


def test_predicate_expression_not_and_binary_repr():
    x = Variable("x")
    pred = Predicate("P", (x,))
    neg = PredicateExpression(PredicateConnective.NOT, pred)
    conj = PredicateExpression(PredicateConnective.AND, pred, pred)
    assert str(neg).startswith("¬")
    assert "∧" in str(conj)


def test_quantified_expression_and_argument_repr():
    x = Variable("x")
    pred = Predicate("Mortal", (x,))
    q = QuantifiedExpression(Quantifier.FORALL, x, pred)
    arg = FOLArgument(premises=(q,), conclusion=pred)
    assert str(q).startswith("∀x")
    assert "Premises:" in str(arg)
