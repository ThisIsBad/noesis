"""String-based parser for propositional logic.

Provides a convenient way to verify logical arguments without
constructing objects manually.

Examples
--------
>>> from logos.parser import verify, parse_argument
>>> result = verify("P -> Q, P |- Q")
>>> print(result.valid)  # True
>>> print(result.rule)   # "Modus Ponens"

>>> result = verify("P -> Q, Q |- P")
>>> print(result.valid)  # False (Affirming the Consequent)

Supported syntax:
    Connectives:
        ->  or  =>      Implication
        <-> or <=>      Biconditional (iff)
        &   or  ^       Conjunction (and)
        |   or  v       Disjunction (or)
        ~   or  !       Negation (not)

    Turnstile:
        |-              Separates premises from conclusion

    Premises are separated by commas.
    Parentheses are supported for grouping.
    Atoms are single uppercase letters (A-Z).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Union

from logos.exceptions import LogicBrainError
from logos.models import (
    Argument,
    Connective,
    LogicalExpression,
    Proposition,
    VerificationResult,
)
from logos.verifier import PropositionalVerifier


# Type alias for expression tree nodes
Expr = Union[Proposition, LogicalExpression]


__all__ = [
    "verify",
    "parse_argument",
    "parse_expression",
    "is_tautology",
    "is_contradiction",
    "are_equivalent",
    "ParseError",
]


class ParseError(LogicBrainError):
    """Raised when parsing fails."""

    pass


@dataclass
class _Token:
    """A lexical token (internal)."""

    type: str
    value: str
    pos: int


class _Lexer:
    """Tokenizes a logic string (internal)."""

    # _Token patterns (order matters - longer patterns first)
    PATTERNS = [
        (r"\s+", None),  # Whitespace (skip)
        (r"<->", "IFF"),  # Biconditional
        (r"<=>", "IFF"),  # Biconditional (alt)
        (r"->", "IMPLIES"),  # Implication
        (r"=>", "IMPLIES"),  # Implication (alt)
        (r"\|-", "TURNSTILE"),  # Turnstile
        (r"&", "AND"),  # Conjunction
        (r"\^", "AND"),  # Conjunction (alt)
        (r"\|", "OR"),  # Disjunction
        (r"v(?![a-zA-Z])", "OR"),  # Disjunction (alt, not followed by letter)
        (r"~", "NOT"),  # Negation
        (r"!", "NOT"),  # Negation (alt)
        (r"\(", "LPAREN"),  # Left paren
        (r"\)", "RPAREN"),  # Right paren
        (r",", "COMMA"),  # Comma
        (r"[A-Z]", "ATOM"),  # Atomic proposition
    ]

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.compiled = [(re.compile(p), t) for p, t in self.PATTERNS]

    def tokenize(self) -> list[_Token]:
        """Convert input string to list of tokens."""
        tokens: list[_Token] = []

        while self.pos < len(self.text):
            match_found = False

            for pattern, token_type in self.compiled:
                match = pattern.match(self.text, self.pos)
                if match:
                    if token_type is not None:  # Skip whitespace
                        tokens.append(_Token(token_type, match.group(), self.pos))
                    self.pos = match.end()
                    match_found = True
                    break

            if not match_found:
                raise ParseError(f"Unexpected character '{self.text[self.pos]}' at position {self.pos}")

        return tokens


class _Parser:
    """Recursive descent parser for propositional logic (internal).

    Grammar (precedence low to high):
        argument    := premises TURNSTILE expr
        premises    := expr (COMMA expr)*
        expr        := iff_expr
        iff_expr    := impl_expr (IFF impl_expr)*
        impl_expr   := or_expr (IMPLIES or_expr)*
        or_expr     := and_expr (OR and_expr)*
        and_expr    := not_expr (AND not_expr)*
        not_expr    := NOT not_expr | atom
        atom        := ATOM | LPAREN expr RPAREN
    """

    def __init__(self, tokens: list[_Token]):
        self.tokens = tokens
        self.pos = 0

    def parse_argument(self) -> Argument:
        """Parse a full argument: premises |- conclusion."""
        premises: list[Expr] = []

        # Parse first premise (required)
        if self.pos >= len(self.tokens):
            raise ParseError("Empty input")

        # Check for empty premises (just "|- conclusion")
        if self.current().type == "TURNSTILE":
            self.advance()
            conclusion = self.parse_expr()
            return Argument(premises=[], conclusion=conclusion)

        # Parse premises
        premises.append(self.parse_expr())

        while self.pos < len(self.tokens) and self.current().type == "COMMA":
            self.advance()  # consume comma
            premises.append(self.parse_expr())

        # Expect turnstile
        if self.pos >= len(self.tokens) or self.current().type != "TURNSTILE":
            raise ParseError(
                f"Expected '|-' (turnstile) after premises. "
                f"Got: {self.current().value if self.pos < len(self.tokens) else 'end of input'}"
            )
        self.advance()  # consume turnstile

        # Parse conclusion
        conclusion = self.parse_expr()

        # Check for leftover tokens
        if self.pos < len(self.tokens):
            raise ParseError(f"Unexpected token after conclusion: '{self.current().value}'")

        return Argument(premises=premises, conclusion=conclusion)

    def parse_expr(self) -> Expr:
        """Parse an expression (entry point)."""
        return self.parse_iff()

    def parse_iff(self) -> Expr:
        """Parse biconditional (lowest precedence binary)."""
        left = self.parse_impl()

        while self.pos < len(self.tokens) and self.current().type == "IFF":
            self.advance()
            right = self.parse_impl()
            left = LogicalExpression(Connective.IFF, left, right)

        return left

    def parse_impl(self) -> Expr:
        """Parse implication (right-associative)."""
        left = self.parse_or()

        if self.pos < len(self.tokens) and self.current().type == "IMPLIES":
            self.advance()
            right = self.parse_impl()  # Right-associative
            return LogicalExpression(Connective.IMPLIES, left, right)

        return left

    def parse_or(self) -> Expr:
        """Parse disjunction."""
        left = self.parse_and()

        while self.pos < len(self.tokens) and self.current().type == "OR":
            self.advance()
            right = self.parse_and()
            left = LogicalExpression(Connective.OR, left, right)

        return left

    def parse_and(self) -> Expr:
        """Parse conjunction."""
        left = self.parse_not()

        while self.pos < len(self.tokens) and self.current().type == "AND":
            self.advance()
            right = self.parse_not()
            left = LogicalExpression(Connective.AND, left, right)

        return left

    def parse_not(self) -> Expr:
        """Parse negation (prefix, highest precedence)."""
        if self.pos < len(self.tokens) and self.current().type == "NOT":
            self.advance()
            operand = self.parse_not()  # Allow chained negation: ~~P
            return LogicalExpression(Connective.NOT, operand)

        return self.parse_atom()

    def parse_atom(self) -> Expr:
        """Parse atomic proposition or parenthesized expression."""
        if self.pos >= len(self.tokens):
            raise ParseError("Unexpected end of input")

        token = self.current()

        if token.type == "ATOM":
            self.advance()
            return Proposition(token.value)

        if token.type == "LPAREN":
            self.advance()
            expr = self.parse_expr()

            if self.pos >= len(self.tokens) or self.current().type != "RPAREN":
                raise ParseError("Missing closing parenthesis")
            self.advance()
            return expr

        raise ParseError(f"Expected atom or '(', got '{token.value}'")

    def current(self) -> _Token:
        """Get current token."""
        return self.tokens[self.pos]

    def advance(self) -> None:
        """Move to next token."""
        self.pos += 1


def parse_expression(text: str) -> Expr:
    """Parse a single logical expression.

    Args:
        text: Expression string like "P -> Q" or "(A & B) | C"

    Returns:
        Parsed expression tree.

    Raises:
        ParseError: If parsing fails.
    """
    lexer = _Lexer(text)
    tokens = lexer.tokenize()

    if not tokens:
        raise ParseError("Empty expression")

    parser = _Parser(tokens)
    return parser.parse_expr()


def parse_argument(text: str) -> Argument:
    """Parse a full argument with premises and conclusion.

    Args:
        text: Argument string like "P -> Q, P |- Q"

    Returns:
        Parsed Argument object.

    Raises:
        ParseError: If parsing fails.
    """
    lexer = _Lexer(text)
    tokens = lexer.tokenize()

    if not tokens:
        raise ParseError("Empty argument")

    parser = _Parser(tokens)
    return parser.parse_argument()


def verify(text: str) -> VerificationResult:
    """Parse and verify a logical argument in one step.

    This is the main convenience function for quick verification.

    Args:
        text: Argument string like "P -> Q, P |- Q"

    Returns:
        VerificationResult with valid/invalid status, rule, and explanation.

    Raises:
        ParseError: If parsing fails.

    Examples:
        >>> result = verify("P -> Q, P |- Q")
        >>> result.valid
        True
        >>> result.rule
        'Modus Ponens'

        >>> result = verify("P -> Q, Q |- P")
        >>> result.valid
        False
        >>> result.rule
        'Affirming the Consequent (fallacy)'
    """
    argument = parse_argument(text)
    verifier = PropositionalVerifier()
    return verifier.verify(argument)


def is_tautology(text: str) -> VerificationResult:
    """Check if an expression is a tautology.

    Args:
        text: Expression string like "P | ~P"

    Returns:
        VerificationResult indicating if the expression is always true.
    """
    expr = parse_expression(text)
    verifier = PropositionalVerifier()
    return verifier.is_tautology(expr)


def is_contradiction(text: str) -> VerificationResult:
    """Check if an expression is a contradiction.

    Args:
        text: Expression string like "P & ~P"

    Returns:
        VerificationResult indicating if the expression is always false.
    """
    expr = parse_expression(text)
    verifier = PropositionalVerifier()
    return verifier.is_contradiction(expr)


def are_equivalent(text_a: str, text_b: str) -> VerificationResult:
    """Check if two expressions are logically equivalent.

    Args:
        text_a: First expression
        text_b: Second expression

    Returns:
        VerificationResult indicating equivalence.
    """
    expr_a = parse_expression(text_a)
    expr_b = parse_expression(text_b)
    verifier = PropositionalVerifier()
    return verifier.check_equivalence(expr_a, expr_b)
