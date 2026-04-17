"""Direct tests for logos.models."""

from __future__ import annotations

import pytest

from logos.models import Argument, Connective, LogicalExpression, Proposition, VerificationResult


def test_logical_expression_not_requires_no_right_operand():
    with pytest.raises(ValueError):
        LogicalExpression(Connective.NOT, Proposition("P"), Proposition("Q"))


def test_logical_expression_binary_requires_right_operand():
    with pytest.raises(ValueError):
        LogicalExpression(Connective.AND, Proposition("P"))


def test_argument_and_verification_result_string_reprs():
    p = Proposition("P")
    arg = Argument(premises=[p], conclusion=p)
    assert "⊢" in str(arg)

    result = VerificationResult(valid=False, rule="Fallacy", explanation="bad", counterexample={"P": False})
    text = str(result)
    assert "INVALID" in text
    assert "Counterexample" in text
