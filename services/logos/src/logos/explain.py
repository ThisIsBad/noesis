"""Human-readable explanation helpers for propositional arguments."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

from logos.models import Argument, Connective, LogicalExpression, Proposition
from logos.parser import parse_argument


Expr = Proposition | LogicalExpression


@dataclass(frozen=True)
class TruthTableRow:
    """One row in a complete truth table."""

    values: dict[str, bool]
    premise_values: list[bool]
    conclusion_value: bool
    all_premises_true: bool


@dataclass(frozen=True)
class TruthTable:
    """Truth-table explanation for a propositional argument."""

    argument_str: str
    propositions: list[str]
    premises: list[str]
    conclusion: str
    rows: list[TruthTableRow]
    valid: bool
    counterexample_rows: list[int]


def truth_table(claim: str) -> TruthTable:
    """Generate a complete truth table for a propositional argument.

    Parameters
    ----------
    claim : str
        Argument in LogicBrain notation, e.g. ``"P -> Q, P |- Q"``.

    Returns
    -------
    TruthTable
        Complete truth table with per-row evaluations.

    Raises
    ------
    ParseError
        If *claim* cannot be parsed.
    ValueError
        If the argument has more than 8 propositions.
    """

    argument = parse_argument(claim)
    propositions = _collect_atoms(argument)
    if len(propositions) > 8:
        raise ValueError("Truth tables are limited to 8 propositions (256 rows maximum).")

    rows: list[TruthTableRow] = []
    counterexample_rows: list[int] = []

    for index, assignment_values in enumerate(product([True, False], repeat=len(propositions))):
        assignment = dict(zip(propositions, assignment_values, strict=True))
        premise_values = [_evaluate_expression(premise, assignment) for premise in argument.premises]
        all_premises_true = all(premise_values)
        conclusion_value = _evaluate_expression(argument.conclusion, assignment)

        row = TruthTableRow(
            values=assignment,
            premise_values=premise_values,
            conclusion_value=conclusion_value,
            all_premises_true=all_premises_true,
        )
        rows.append(row)

        if all_premises_true and not conclusion_value:
            counterexample_rows.append(index)

    return TruthTable(
        argument_str=claim,
        propositions=propositions,
        premises=[str(premise) for premise in argument.premises],
        conclusion=str(argument.conclusion),
        rows=rows,
        valid=not counterexample_rows,
        counterexample_rows=counterexample_rows,
    )


def render_truth_table(table: TruthTable) -> str:
    """Render a ``TruthTable`` as a formatted string."""

    headers = [
        *table.propositions,
        *table.premises,
        table.conclusion,
        "Alle Praemissen wahr?",
        "Konklusion?",
        "Mark",
    ]

    rendered_rows: list[list[str]] = []
    for index, row in enumerate(table.rows):
        rendered_rows.append(
            [
                *[_render_bool(row.values[label]) for label in table.propositions],
                *[_render_bool(value) for value in row.premise_values],
                _render_bool(row.conclusion_value),
                _render_bool(row.all_premises_true),
                _render_bool(row.conclusion_value),
                "⚠️" if index in table.counterexample_rows else "",
            ]
        )

    widths = [len(header) for header in headers]
    for rendered_row in rendered_rows:
        for i, cell in enumerate(rendered_row):
            widths[i] = max(widths[i], len(cell))

    lines = [f"Argument: {table.argument_str}"]
    lines.append(_format_row(headers, widths))
    lines.append(_format_rule(widths))
    lines.extend(_format_row(row, widths) for row in rendered_rows)

    if table.valid:
        lines.append("Summary: ✓ Valid - no counterexample rows.")
    else:
        lines.append(
            "Summary: ✗ Invalid - counterexample rows: " + ", ".join(str(index) for index in table.counterexample_rows)
        )

    return "\n".join(lines)


def _collect_atoms(argument: Argument) -> list[str]:
    atoms: set[str] = set()
    for premise in argument.premises:
        _collect_atoms_from_expr(premise, atoms)
    _collect_atoms_from_expr(argument.conclusion, atoms)
    return sorted(atoms)


def _collect_atoms_from_expr(expr: Expr, atoms: set[str]) -> None:
    if isinstance(expr, Proposition):
        atoms.add(expr.label)
        return
    _collect_atoms_from_expr(expr.left, atoms)
    if expr.right is not None:
        _collect_atoms_from_expr(expr.right, atoms)


def _evaluate_expression(expr: Expr, assignment: dict[str, bool]) -> bool:
    if isinstance(expr, Proposition):
        return assignment[expr.label]

    left = _evaluate_expression(expr.left, assignment)

    if expr.connective is Connective.NOT:
        return not left

    if expr.right is None:
        raise ValueError(f"Binary connective {expr.connective} requires right operand")

    right = _evaluate_expression(expr.right, assignment)
    if expr.connective is Connective.AND:
        return left and right
    if expr.connective is Connective.OR:
        return left or right
    if expr.connective is Connective.IMPLIES:
        return (not left) or right
    if expr.connective is Connective.IFF:
        return left == right
    raise ValueError(f"Unknown connective: {expr.connective}")


def _render_bool(value: bool) -> str:
    return "T" if value else "F"


def _format_row(values: list[str], widths: list[int]) -> str:
    return " | ".join(value.ljust(width) for value, width in zip(values, widths, strict=True))


def _format_rule(widths: list[int]) -> str:
    return "-+-".join("-" * width for width in widths)


__all__ = ["TruthTable", "TruthTableRow", "truth_table", "render_truth_table"]
