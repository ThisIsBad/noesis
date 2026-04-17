"""Metamorphic tests for propositional verifier semantics (Issue #27)."""

from __future__ import annotations

import pytest

from logos import verify


pytestmark = pytest.mark.metamorphic


def _assert_same_validity(source_argument: str, transformed_argument: str) -> None:
    source = verify(source_argument)
    transformed = verify(transformed_argument)

    assert transformed.valid is source.valid, (
        "Metamorphic relation violated:\n"
        f"  source:      {source_argument} -> valid={source.valid}\n"
        f"  transformed: {transformed_argument} -> valid={transformed.valid}"
    )


@pytest.mark.parametrize(
    ("source_argument", "transformed_argument"),
    [
        # Implication rewrite: (A -> B)  <=>  (~A | B)
        pytest.param("P -> Q, P |- Q", "(~P | Q), P |- Q", id="implication-rewrite-mp"),
        pytest.param("R -> S, ~S |- ~R", "(~R | S), ~S |- ~R", id="implication-rewrite-mt"),
        # Double negation
        pytest.param("~~P |- P", "P |- P", id="double-negation-elim"),
        pytest.param("P |- ~~P", "P |- P", id="double-negation-intro"),
        # Commutativity
        pytest.param("P & Q |- Q & P", "Q & P |- P & Q", id="commutativity-and"),
        pytest.param("P |- P | Q", "P |- Q | P", id="commutativity-or"),
        # Associativity
        pytest.param(
            "(P & Q) & R |- P & (Q & R)",
            "P & (Q & R) |- (P & Q) & R",
            id="associativity-and",
        ),
        pytest.param(
            "(P | Q) | R, ~P, ~Q |- R",
            "P | (Q | R), ~P, ~Q |- R",
            id="associativity-or",
        ),
        # De Morgan rewrites
        pytest.param("~(P & Q), P |- ~Q", "(~P | ~Q), P |- ~Q", id="de-morgan-and"),
        pytest.param("~(P | Q), P |- ~Q", "(~P & ~Q), P |- ~Q", id="de-morgan-or"),
    ],
)
def test_metamorphic_relations_preserve_validity(
    source_argument: str,
    transformed_argument: str,
) -> None:
    _assert_same_validity(source_argument, transformed_argument)
