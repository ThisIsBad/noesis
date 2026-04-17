"""Metamorphic parser tests for syntax-preserving transformations (Issue #25)."""

from __future__ import annotations

import pytest

from logos import verify


pytestmark = pytest.mark.metamorphic


def _assert_same_outcome(source_argument: str, transformed_argument: str) -> None:
    source = verify(source_argument)
    transformed = verify(transformed_argument)

    assert transformed.valid is source.valid, (
        "Parser metamorphic relation violated:\n"
        f"  source:      {source_argument} -> valid={source.valid}\n"
        f"  transformed: {transformed_argument} -> valid={transformed.valid}"
    )


@pytest.mark.parametrize(
    ("source_argument", "transformed_argument"),
    [
        # Whitespace and line-break invariance
        pytest.param("P -> Q, P |- Q", "   P   ->   Q  ,   P   |-   Q   ", id="whitespace-padding"),
        pytest.param("P -> Q, Q |- P", "P -> Q,\nQ |- P", id="newline-premise-break"),
        # Parentheses insertion/removal where precedence stays equivalent
        pytest.param("P -> Q, P |- Q", "((P -> Q)), (P) |- (Q)", id="parentheses-redundant"),
        pytest.param("~P & Q |- Q", "(~P) & (Q) |- (Q)", id="parentheses-unary-binary"),
        # Operator alias equivalence
        pytest.param("P -> Q, ~Q |- ~P", "P => Q, !Q |- !P", id="alias-imp-not"),
        pytest.param("P <-> Q |- Q <-> P", "P <=> Q |- Q <=> P", id="alias-iff"),
        pytest.param("P & Q |- P", "P ^ Q |- P", id="alias-and"),
        # Premise ordering invariance
        pytest.param("P -> Q, P, R |- Q", "R, P, P -> Q |- Q", id="premise-order"),
    ],
)
def test_parser_metamorphic_relations_preserve_outcome(
    source_argument: str,
    transformed_argument: str,
) -> None:
    _assert_same_outcome(source_argument, transformed_argument)
