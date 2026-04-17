"""Tests for human-readable truth-table explanations."""

from __future__ import annotations

import pytest

from logos import ParseError, render_truth_table, truth_table


def test_truth_table_modus_ponens() -> None:
    table = truth_table("P -> Q, P |- Q")

    assert table.valid is True
    assert len(table.rows) == 4
    assert table.counterexample_rows == []


def test_truth_table_affirming_consequent() -> None:
    table = truth_table("P -> Q, Q |- P")

    assert table.valid is False
    assert len(table.rows) == 4
    assert table.counterexample_rows == [2]


def test_truth_table_three_props() -> None:
    table = truth_table("P -> Q, Q -> R |- P -> R")

    assert len(table.rows) == 8
    assert table.propositions == ["P", "Q", "R"]


def test_truth_table_tautology() -> None:
    table = truth_table("|- P | ~P")

    assert table.valid is True
    assert all(row.conclusion_value for row in table.rows)
    assert all(row.all_premises_true for row in table.rows)


def test_truth_table_too_many_props() -> None:
    with pytest.raises(ValueError, match="8 propositions"):
        truth_table("A, B, C, D, E, F, G, H, I |- A")


def test_truth_table_parse_error() -> None:
    with pytest.raises(ParseError):
        truth_table("P -> |- Q")


def test_render_truth_table_contains_headers() -> None:
    rendered = render_truth_table(truth_table("P -> Q, P |- Q"))

    assert "P" in rendered
    assert "Q" in rendered
    assert "Konklusion" in rendered


def test_render_truth_table_marks_counterexample() -> None:
    rendered = render_truth_table(truth_table("P -> Q, Q |- P"))

    assert "⚠️" in rendered


def test_render_valid_shows_checkmark() -> None:
    rendered = render_truth_table(truth_table("P -> Q, P |- Q"))

    assert "✓" in rendered
