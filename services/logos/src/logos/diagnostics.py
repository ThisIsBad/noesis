"""Structured diagnostics for proof and constraint errors.

This module provides rich error information to help agents understand
and recover from failures in proving or constraint solving.

Example
-------
>>> result = session.apply("apply Nat.add_comm")
>>> if not result.success:
...     print(result.diagnostic.error_type)    # "type_mismatch"
...     print(result.diagnostic.expected)      # "a + b = b + a"
...     print(result.diagnostic.actual)        # "a * b = b * a"
...     print(result.diagnostic.suggestions)   # ["Try: apply Nat.mul_comm"]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorType(Enum):
    """Categories of errors for structured handling."""

    # Lean/Proof errors
    UNKNOWN_TACTIC = "unknown_tactic"
    TACTIC_FAILED = "tactic_failed"
    TYPE_MISMATCH = "type_mismatch"
    UNKNOWN_IDENTIFIER = "unknown_identifier"
    SYNTAX_ERROR = "syntax_error"
    TIMEOUT = "timeout"

    # Z3/Constraint errors
    UNSATISFIABLE = "unsatisfiable"
    UNDECLARED_VARIABLE = "undeclared_variable"
    INVALID_SORT = "invalid_sort"
    PARSE_ERROR = "parse_error"

    # Generic
    UNKNOWN = "unknown"
    INTERNAL_ERROR = "internal_error"


@dataclass
class Diagnostic:
    """Structured diagnostic information for an error.
    
    This class provides detailed, machine-readable information about
    errors that occur during proving or constraint solving, making it
    easier for agents to understand and recover from failures.
    
    The ``schema_version`` field allows agents to check compatibility
    before processing diagnostics.
    """

    error_type: ErrorType
    """Category of the error."""

    message: str
    """Human-readable error message."""

    schema_version: str = "1"
    """Schema version for forward-compatibility checks."""

    expected: str | None = None
    """What was expected (e.g., expected type)."""

    actual: str | None = None
    """What was actually found (e.g., actual type)."""

    location: str | None = None
    """Location of the error (e.g., line:column)."""

    context: str | None = None
    """Additional context (e.g., surrounding code)."""

    suggestions: list[str] = field(default_factory=list)
    """Suggested fixes or alternatives."""

    raw_output: str | None = None
    """The raw error output for debugging."""

    def __str__(self) -> str:
        """Format diagnostic as a readable string."""
        parts = [f"[{self.error_type.value}] {self.message}"]

        if self.expected and self.actual:
            parts.append(f"  Expected: {self.expected}")
            parts.append(f"  Actual:   {self.actual}")
        elif self.expected:
            parts.append(f"  Expected: {self.expected}")
        elif self.actual:
            parts.append(f"  Found: {self.actual}")

        if self.location:
            parts.append(f"  At: {self.location}")

        if self.suggestions:
            parts.append("  Suggestions:")
            for s in self.suggestions:
                parts.append(f"    - {s}")

        return "\n".join(parts)


class LeanDiagnosticParser:
    """Parser for Lean 4 error messages to extract structured diagnostics."""

    # Patterns for common Lean errors
    PATTERNS = {
        ErrorType.UNKNOWN_TACTIC: [
            r"unknown tactic '(\w+)'",
            r"unknown identifier '(\w+)'.*tactic",
        ],
        ErrorType.TYPE_MISMATCH: [
            r"type mismatch",
            r"has type\s+(.+?)\s+but is expected to have type\s+(.+)",
        ],
        ErrorType.UNKNOWN_IDENTIFIER: [
            r"unknown identifier '([^']+)'",
            r"unknown constant '([^']+)'",
        ],
        ErrorType.TACTIC_FAILED: [
            r"tactic '(\w+)' failed",
            r"failed to synthesize",
        ],
        ErrorType.SYNTAX_ERROR: [
            r"unexpected token",
            r"expected .+",
            r"unexpected end of input",
        ],
    }

    # Suggestion mappings for common errors
    SUGGESTIONS = {
        "rfl": [
            "If types differ, try 'simp' or 'ring' instead",
            "For definitional equality, ensure both sides reduce to the same term",
        ],
        "simp": [
            "Try 'simp only [lemma_name]' for more control",
            "Add '?' to see what simp tried: 'simp?'",
        ],
        "apply": [
            "Check that the lemma's conclusion matches your goal",
            "Use 'exact' if the term has the exact required type",
        ],
        "exact": [
            "If types are definitionally equal, try 'exact?' to search",
            "Consider using 'apply' if you need to provide arguments",
        ],
        "induction": [
            "Make sure the variable is in scope",
            "Try 'induction x with ...' to name cases",
        ],
    }

    # Common tactic typos and corrections
    TYPO_CORRECTIONS = {
        "reflexivity": "rfl",
        "refl": "rfl",
        "simplify": "simp",
        "intro": "intro",
        "intros": "intro",
        "assumption": "assumption",
        "trivial": "trivial",
        "decide": "decide",
        "native_decide": "native_decide",
        "ring": "ring",
        "linarith": "linarith",
        "omega": "omega",
        "norm_num": "norm_num",
    }

    @classmethod
    def parse(cls, error_output: str, tactic: str | None = None) -> Diagnostic:
        """Parse Lean error output into a structured Diagnostic.
        
        Parameters
        ----------
        error_output : str
            The raw error output from Lean.
        tactic : str, optional
            The tactic that was attempted.
        
        Returns
        -------
        Diagnostic
            Structured diagnostic information.
        """
        error_type = cls._identify_error_type(error_output)
        message = cls._extract_message(error_output)
        expected, actual = cls._extract_types(error_output)
        location = cls._extract_location(error_output)
        suggestions = cls._generate_suggestions(error_output, tactic, error_type)

        return Diagnostic(
            error_type=error_type,
            message=message,
            expected=expected,
            actual=actual,
            location=location,
            suggestions=suggestions,
            raw_output=error_output,
        )

    @classmethod
    def _identify_error_type(cls, output: str) -> ErrorType:
        """Identify the type of error from the output."""
        output_lower = output.lower()

        for error_type, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, output, re.IGNORECASE):
                    return error_type

        if "error:" in output_lower:
            return ErrorType.UNKNOWN

        return ErrorType.UNKNOWN

    @classmethod
    def _extract_message(cls, output: str) -> str:
        """Extract the main error message."""
        # Look for "error: <message>"
        match = re.search(r'error:\s*(.+?)(?:\n|$)', output, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Fallback: first non-empty line
        for line in output.split('\n'):
            line = line.strip()
            if line and not line.startswith(('/', 'temp', 'logos')):
                return line

        return "Unknown error"

    @classmethod
    def _extract_types(cls, output: str) -> tuple[str | None, str | None]:
        """Extract expected and actual types from type mismatch errors."""
        # Pattern: "has type X but is expected to have type Y"
        match = re.search(
            r'has type\s+(.+?)\s+but is expected to have type\s+(.+)',
            output,
            re.DOTALL
        )
        if match:
            actual = match.group(1).strip()
            expected = match.group(2).strip()
            return expected, actual

        # Pattern: "expected X, got Y"
        match = re.search(r'expected\s+(.+?),\s*got\s+(.+)', output, re.IGNORECASE)
        if match:
            return match.group(1).strip(), match.group(2).strip()

        return None, None

    @classmethod
    def _extract_location(cls, output: str) -> str | None:
        """Extract error location (file:line:column)."""
        match = re.search(r'(\S+\.lean):(\d+):(\d+)', output)
        if match:
            return f"line {match.group(2)}, column {match.group(3)}"
        return None

    @classmethod
    def _generate_suggestions(
        cls,
        output: str,
        tactic: str | None,
        error_type: ErrorType
    ) -> list[str]:
        """Generate suggestions based on the error."""
        suggestions = []

        # Add tactic-specific suggestions
        if tactic:
            tactic_name = tactic.split()[0].lower()
            if tactic_name in cls.SUGGESTIONS:
                suggestions.extend(cls.SUGGESTIONS[tactic_name])

        # Check for typos
        if error_type == ErrorType.UNKNOWN_TACTIC and tactic:
            tactic_name = tactic.split()[0].lower()
            # Find similar tactics
            for typo, correct in cls.TYPO_CORRECTIONS.items():
                if cls._similar(tactic_name, typo):
                    suggestions.append(f"Did you mean: {correct}")
                    break

        # Type mismatch suggestions
        if error_type == ErrorType.TYPE_MISMATCH:
            suggestions.append("Check that the types are compatible")
            suggestions.append("Consider using a conversion tactic")

        # Unknown identifier suggestions
        if error_type == ErrorType.UNKNOWN_IDENTIFIER:
            match = re.search(r"unknown identifier '([^']+)'", output)
            if match:
                name = match.group(1)
                suggestions.append(f"Check spelling of '{name}'")
                suggestions.append("Ensure required imports are present")

        return suggestions

    @staticmethod
    def _similar(s1: str, s2: str) -> bool:
        """Check if two strings are similar (simple Levenshtein-like)."""
        if s1 == s2:
            return True
        if abs(len(s1) - len(s2)) > 2:
            return False

        # Check for prefix match
        min_len = min(len(s1), len(s2))
        if min_len >= 3 and s1[:3] == s2[:3]:
            return True

        # Check for single character difference
        diffs = sum(1 for a, b in zip(s1, s2) if a != b)
        return diffs <= 1


class Z3DiagnosticParser:
    """Parser for Z3 errors to extract structured diagnostics."""

    @classmethod
    def parse_unsat(
        cls,
        constraints: list[str],
        unsat_core: list[str] | None = None,
        model_before: dict[str, Any] | None = None,
    ) -> Diagnostic:
        """Create diagnostic for unsatisfiable constraints.
        
        Parameters
        ----------
        constraints : list[str]
            The list of asserted constraints.
        unsat_core : list[str], optional
            Names of constraints in the unsat core.
        model_before : dict, optional
            The model before the conflicting constraint was added.
        """
        suggestions = []

        if unsat_core:
            suggestions.append(
                f"Conflicting constraints: {', '.join(unsat_core)}"
            )
            suggestions.append("Try removing or weakening one of these constraints")
        else:
            suggestions.append("Use track_unsat_core=True to identify conflicting constraints")

        if len(constraints) <= 3:
            suggestions.append(
                "With few constraints, check each one manually for contradictions"
            )

        return Diagnostic(
            error_type=ErrorType.UNSATISFIABLE,
            message="Constraints are unsatisfiable (no solution exists)",
            context=f"{len(constraints)} constraints asserted",
            suggestions=suggestions,
        )

    @classmethod
    def parse_constraint_error(cls, error: str, constraint: str) -> Diagnostic:
        """Create diagnostic for constraint parsing errors."""

        error_lower = error.lower()

        if (
            "undeclared" in error_lower
            or "undefined" in error_lower
            or "not defined" in error_lower
            or "is not defined" in error_lower
        ):
            # Extract variable name
            match = re.search(r"'(\w+)'", error)
            var_name = match.group(1) if match else "variable"

            return Diagnostic(
                error_type=ErrorType.UNDECLARED_VARIABLE,
                message=f"Variable '{var_name}' not declared",
                actual=constraint,
                suggestions=[
                    f"Declare the variable first: session.declare('{var_name}', 'Int')",
                    "Check spelling of variable names",
                ],
            )

        if "sort" in error.lower() or "type" in error.lower():
            return Diagnostic(
                error_type=ErrorType.INVALID_SORT,
                message="Type/sort mismatch in constraint",
                actual=constraint,
                suggestions=[
                    "Ensure all variables have compatible types",
                    "Check that arithmetic operations match variable sorts",
                ],
            )

        return Diagnostic(
            error_type=ErrorType.PARSE_ERROR,
            message=f"Failed to parse constraint: {error}",
            actual=constraint,
            suggestions=[
                "Check constraint syntax",
                "Supported: +, -, *, /, >, <, >=, <=, ==, !=, And, Or, Not",
            ],
            raw_output=error,
        )
