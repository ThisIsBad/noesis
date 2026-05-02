"""Data models for structured logic representation.

These models form the bridge between natural-language reasoning and
the deterministic Z3 verifier. Every logical argument — no matter how
complex — is decomposed into Propositions, LogicalExpressions, and
an Argument (premises → conclusion).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Connective enum
# ---------------------------------------------------------------------------


class Connective(Enum):
    """Logical connectives supported by the framework."""

    AND = "AND"
    OR = "OR"
    NOT = "NOT"  # unary — only uses `left`
    IMPLIES = "IMPLIES"  # left → right
    IFF = "IFF"  # left ↔ right


# ---------------------------------------------------------------------------
# Core expression tree
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Proposition:
    """An atomic proposition, e.g. 'It is raining' → Proposition('P')."""

    label: str

    def __str__(self) -> str:
        return self.label


@dataclass(frozen=True)
class LogicalExpression:
    """Recursive tree representing a compound logical expression.

    Examples
    --------
    >>> p = Proposition("P")
    >>> q = Proposition("Q")
    >>> p_implies_q = LogicalExpression(Connective.IMPLIES, p, q)
    >>> not_p = LogicalExpression(Connective.NOT, p)
    """

    connective: Connective
    left: Proposition | LogicalExpression
    right: Proposition | LogicalExpression | None = None

    def __post_init__(self) -> None:
        if self.connective is Connective.NOT:
            if self.right is not None:
                raise ValueError("NOT is unary — 'right' must be None.")
        else:
            if self.right is None:
                raise ValueError(f"{self.connective.value} is binary — 'right' is required.")

    def __str__(self) -> str:
        if self.connective is Connective.NOT:
            return f"¬{self.left}"
        symbols = {
            Connective.AND: "∧",
            Connective.OR: "∨",
            Connective.IMPLIES: "→",
            Connective.IFF: "↔",
        }
        return f"({self.left} {symbols[self.connective]} {self.right})"


# ---------------------------------------------------------------------------
# Argument = premises + conclusion
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Argument:
    """A logical argument: a set of premises leading to a conclusion.

    Parameters
    ----------
    premises : list of Proposition | LogicalExpression
        The assumed-true statements.
    conclusion : Proposition | LogicalExpression
        The statement claimed to follow from the premises.
    natural_language : str, optional
        The original natural-language formulation (for reporting).
    """

    premises: list[Proposition | LogicalExpression]
    conclusion: Proposition | LogicalExpression
    natural_language: str = ""

    def __str__(self) -> str:
        prems = ", ".join(str(p) for p in self.premises)
        return f"{prems} ⊢ {self.conclusion}"


# ---------------------------------------------------------------------------
# Verification result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of verifying an Argument against the deterministic engine.

    Parameters
    ----------
    valid : bool
        True if the conclusion follows necessarily from the premises.
    counterexample : dict | None
        If invalid, a truth-value assignment that satisfies the premises
        but falsifies the conclusion.
    rule : str
        Name of the logical rule or fallacy identified.
    explanation : str
        Human-readable explanation of *why* the argument is valid/invalid.
    """

    valid: bool
    counterexample: dict[str, Any] | None = None
    rule: str = ""
    explanation: str = ""

    def __str__(self) -> str:
        status = "✅ VALID" if self.valid else "❌ INVALID"
        parts = [status]
        if self.rule:
            parts.append(f"[{self.rule}]")
        if self.explanation:
            parts.append(self.explanation)
        if self.counterexample:
            parts.append(f"Counterexample: {self.counterexample}")
        return " — ".join(parts)
