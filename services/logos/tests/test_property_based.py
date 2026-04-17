"""Property-based and fuzz tests for propositional parsing and verification."""

from __future__ import annotations

import string

from hypothesis import given, settings
from hypothesis import strategies as st

from logos.parser import (
    ParseError,
    are_equivalent,
    is_contradiction,
    is_tautology,
    parse_argument,
    parse_expression,
    verify,
)


ATOM_STRATEGY = st.sampled_from(list("PQRS"))
OP_STRATEGY = st.sampled_from(["&", "|", "->", "<->"])


@st.composite
def expr_strings(draw: st.DrawFn) -> str:
    """Generate valid propositional expressions as parser input strings."""

    recursive = st.recursive(
        ATOM_STRATEGY,
        lambda child: st.one_of(
            child.map(lambda e: f"~{e}"),
            st.tuples(child, OP_STRATEGY, child).map(lambda t: f"({t[0]} {t[1]} {t[2]})"),
        ),
        max_leaves=12,
    )
    return draw(recursive)


@given(expr=expr_strings())
@settings(max_examples=80)
def test_reflexive_argument_is_always_valid(expr: str):
    result = verify(f"{expr} |- {expr}")
    assert result.valid is True


@given(expr=expr_strings())
@settings(max_examples=60)
def test_excluded_middle_generated_expression_is_tautology(expr: str):
    result = is_tautology(f"({expr}) | ~({expr})")
    assert result.valid is True


@given(expr=expr_strings())
@settings(max_examples=60)
def test_non_contradiction_generated_expression(expr: str):
    result = is_contradiction(f"({expr}) & ~({expr})")
    assert result.valid is True


@given(a=expr_strings(), b=expr_strings())
@settings(max_examples=70)
def test_material_implication_equivalence_property(a: str, b: str):
    result = are_equivalent(f"({a}) -> ({b})", f"~({a}) | ({b})")
    assert result.valid is True


@given(
    premises=st.lists(expr_strings(), min_size=0, max_size=4),
    conclusion=expr_strings(),
)
@settings(max_examples=60)
def test_generated_arguments_parse_without_crashing(premises: list[str], conclusion: str):
    if premises:
        argument = f"{', '.join(premises)} |- {conclusion}"
    else:
        argument = f"|- {conclusion}"

    parsed = parse_argument(argument)
    assert parsed is not None


@given(
    text=st.text(
        alphabet=list(string.ascii_letters + string.digits + "!@#$%^&*()_+-=|~<>,.?/ "),
        min_size=1,
        max_size=50,
    )
)
@settings(max_examples=120)
def test_expression_fuzzing_raises_only_parse_error_or_parses(text: str):
    try:
        parse_expression(text)
    except ParseError:
        pass
