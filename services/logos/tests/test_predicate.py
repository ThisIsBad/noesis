import pytest
from logos.predicate_models import (
    Variable,
    Constant,
    Predicate,
    PredicateConnective,
    PredicateExpression,
    QuantifiedExpression,
    Quantifier,
    FOLArgument,
)
from logos.predicate import PredicateVerifier


@pytest.fixture
def verifier():
    return PredicateVerifier()


def test_socrates_syllogism(verifier):
    # Forall x (Man(x) -> Mortal(x))
    # Man(Socrates)
    # ---------------------------
    # Mortal(Socrates)

    x = Variable("x")
    socrates = Constant("Socrates")

    # Man(x) -> Mortal(x)
    man_x = Predicate("Man", (x,))
    mortal_x = Predicate("Mortal", (x,))
    impl = PredicateExpression(PredicateConnective.IMPLIES, man_x, mortal_x)

    # Forall x
    p1 = QuantifiedExpression(Quantifier.FORALL, x, impl)

    # Man(Socrates)
    p2 = Predicate("Man", (socrates,))

    # Conclusion: Mortal(Socrates)
    conc = Predicate("Mortal", (socrates,))

    arg = FOLArgument(premises=(p1, p2), conclusion=conc)

    res = verifier.verify(arg)
    assert res.valid is True


def test_invalid_socrates(verifier):
    # Forall x (Man(x) -> Mortal(x))
    # Mortal(Socrates)
    # ---------------------------
    # Man(Socrates)  # Invalid: Affirming the consequent

    x = Variable("x")
    socrates = Constant("Socrates")

    man_x = Predicate("Man", (x,))
    mortal_x = Predicate("Mortal", (x,))
    impl = PredicateExpression(PredicateConnective.IMPLIES, man_x, mortal_x)

    p1 = QuantifiedExpression(Quantifier.FORALL, x, impl)
    p2 = Predicate("Mortal", (socrates,))

    conc = Predicate("Man", (socrates,))

    arg = FOLArgument(premises=(p1, p2), conclusion=conc)

    res = verifier.verify(arg)
    assert res.valid is False


def test_exists_introduction(verifier):
    # Happy(John)
    # ---------------------------
    # Exists x Happy(x)

    john = Constant("John")
    x = Variable("x")

    p1 = Predicate("Happy", (john,))

    happy_x = Predicate("Happy", (x,))
    conc = QuantifiedExpression(Quantifier.EXISTS, x, happy_x)

    arg = FOLArgument(premises=(p1,), conclusion=conc)
    res = verifier.verify(arg)
    assert res.valid is True


def test_quantifier_swap_valid(verifier):
    # Exists y Forall x Loves(x, y)
    # ---------------------------
    # Forall x Exists y Loves(x, y)

    x = Variable("x")
    y = Variable("y")

    loves_xy = Predicate("Loves", (x, y))

    # Exists y Forall x Loves(x,y)
    p1_inner = QuantifiedExpression(Quantifier.FORALL, x, loves_xy)
    p1 = QuantifiedExpression(Quantifier.EXISTS, y, p1_inner)

    # Forall x Exists y Loves(x,y)
    conc_inner = QuantifiedExpression(Quantifier.EXISTS, y, loves_xy)
    conc = QuantifiedExpression(Quantifier.FORALL, x, conc_inner)

    arg = FOLArgument(premises=(p1,), conclusion=conc)
    res = verifier.verify(arg)
    assert res.valid is True


def test_quantifier_swap_invalid(verifier):
    # Forall x Exists y Loves(x, y)
    # ---------------------------
    # Exists y Forall x Loves(x, y)

    x = Variable("x")
    y = Variable("y")

    loves_xy = Predicate("Loves", (x, y))

    p1_inner = QuantifiedExpression(Quantifier.EXISTS, y, loves_xy)
    p1 = QuantifiedExpression(Quantifier.FORALL, x, p1_inner)

    conc_inner = QuantifiedExpression(Quantifier.FORALL, x, loves_xy)
    conc = QuantifiedExpression(Quantifier.EXISTS, y, conc_inner)

    arg = FOLArgument(premises=(p1,), conclusion=conc)
    res = verifier.verify(arg)
    assert res.valid is False


def test_De_Morgan_for_quantifiers(verifier):
    # ~Forall x P(x)
    # ---------------------------
    # Exists x ~P(x)

    x = Variable("x")
    p_x = Predicate("P", (x,))

    forall_px = QuantifiedExpression(Quantifier.FORALL, x, p_x)
    p1 = PredicateExpression(PredicateConnective.NOT, forall_px)

    not_px = PredicateExpression(PredicateConnective.NOT, p_x)
    conc = QuantifiedExpression(Quantifier.EXISTS, x, not_px)

    arg = FOLArgument(premises=(p1,), conclusion=conc)
    res = verifier.verify(arg)
    assert res.valid is True
