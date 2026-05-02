"""Benchmark loader — deserialises problems.json into model objects.

Internal module — not part of the public API (Tier 3).
"""

from __future__ import annotations

__all__ = ["load_problems", "parse_problem"]

import json
from pathlib import Path
from typing import Any, cast

from logos.models import (
    Argument,
    Connective,
    LogicalExpression,
    Proposition,
)


def _find_benchmarks_dir() -> Path:
    """Locate the benchmarks/ directory, supporting both flat and src/ layouts."""
    here = Path(__file__).resolve().parent
    for candidate in (here.parent / "benchmarks", here.parent.parent / "benchmarks"):
        if candidate.is_dir():
            return candidate
    return here.parent / "benchmarks"


BENCHMARKS_DIR = _find_benchmarks_dir()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_problems(path: Path | None = None) -> list[dict[str, Any]]:
    """Load raw problem dicts from the JSON file."""
    path = path or (BENCHMARKS_DIR / "problems.json")
    with open(path, encoding="utf-8") as f:
        data = cast(dict[str, Any], json.load(f))
    return cast(list[dict[str, Any]], data["problems"])


def parse_problem(raw: dict[str, Any]) -> tuple[Argument, dict[str, Any]]:
    """Parse a raw problem dict into an Argument + metadata.

    Returns (argument, metadata) where metadata contains id, level,
    category, expected_valid, explanation, natural_language.
    """
    premises = [_parse_expr(p) for p in raw["premises"]]
    conclusion = _parse_expr(raw["conclusion"])
    arg = Argument(
        premises=premises,
        conclusion=conclusion,
        natural_language=raw.get("natural_language", ""),
    )
    meta = {
        "id": raw["id"],
        "level": raw["level"],
        "category": raw["category"],
        "expected_valid": raw["expected_valid"],
        "explanation": raw.get("explanation", ""),
    }
    return arg, meta


# ---------------------------------------------------------------------------
# Expression parser
# ---------------------------------------------------------------------------


def _parse_expr(data: Any) -> Proposition | LogicalExpression:
    """Recursively parse a JSON expression into model objects."""
    # Bare string → atomic proposition
    if isinstance(data, str):
        return Proposition(data)

    if not isinstance(data, dict):
        raise ValueError(f"Cannot parse expression: {data!r}")

    expr_type = data["type"]

    if expr_type == "atom":
        return Proposition(data["label"])

    if expr_type == "not":
        operand = _parse_expr(data["operand"])
        return LogicalExpression(Connective.NOT, operand)

    if expr_type == "and":
        return LogicalExpression(Connective.AND, _parse_expr(data["left"]), _parse_expr(data["right"]))

    if expr_type == "or":
        return LogicalExpression(Connective.OR, _parse_expr(data["left"]), _parse_expr(data["right"]))

    if expr_type == "implies":
        return LogicalExpression(Connective.IMPLIES, _parse_expr(data["left"]), _parse_expr(data["right"]))

    if expr_type == "iff":
        return LogicalExpression(Connective.IFF, _parse_expr(data["left"]), _parse_expr(data["right"]))

    raise ValueError(f"Unknown expression type: {expr_type!r}")
