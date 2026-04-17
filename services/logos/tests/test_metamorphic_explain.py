"""Metamorphic tests for truth-table explanations."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from logos import truth_table, verify


pytestmark = pytest.mark.metamorphic

ATOM_STRATEGY = st.sampled_from(list("PQRS"))
OP_STRATEGY = st.sampled_from(["&", "|", "->", "<->"])


@st.composite
def expr_strings(draw: st.DrawFn) -> str:
    recursive = st.recursive(
        ATOM_STRATEGY,
        lambda child: st.one_of(
            child.map(lambda expr: f"~{expr}"),
            st.tuples(child, OP_STRATEGY, child).map(
                lambda parts: f"({parts[0]} {parts[1]} {parts[2]})"
            ),
        ),
        max_leaves=8,
    )
    return draw(recursive)


@st.composite
def argument_strings(draw: st.DrawFn) -> str:
    premises = draw(st.lists(expr_strings(), min_size=0, max_size=3))
    conclusion = draw(expr_strings())
    if premises:
        return f"{', '.join(premises)} |- {conclusion}"
    return f"|- {conclusion}"


@given(claim=argument_strings())
@settings(max_examples=60)
def test_truth_table_row_count_is_2_pow_n(claim: str) -> None:
    table = truth_table(claim)

    assert len(table.rows) == 2 ** len(table.propositions)


@given(claim=argument_strings())
@settings(max_examples=60)
def test_truth_table_validity_matches_verify(claim: str) -> None:
    assert truth_table(claim).valid is verify(claim).valid
