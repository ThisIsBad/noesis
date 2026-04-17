"""Command-line interface for quick propositional argument verification."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from logos.models import VerificationResult
from logos.parser import ParseError, verify


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m logos",
        description="Verify propositional logic arguments like 'P -> Q, P |- Q'.",
    )
    parser.add_argument(
        "argument",
        help="Logical argument to verify, e.g. \"P -> Q, P |- Q\"",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Include explanation and counterexample details",
    )
    return parser


def _result_to_dict(result: VerificationResult, include_explanation: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "valid": result.valid,
        "rule": result.rule,
    }
    if include_explanation:
        payload["explanation"] = result.explanation
        payload["counterexample"] = result.counterexample
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        result = verify(args.argument)
    except ParseError as exc:
        if args.json:
            error_payload = {
                "error": "parse_error",
                "message": str(exc),
            }
            print(json.dumps(error_payload, ensure_ascii=True))
        else:
            print(f"ParseError: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(_result_to_dict(result, args.explain), ensure_ascii=True))
        return 0

    print(f"valid={result.valid}")
    print(f"rule={result.rule}")
    if args.explain:
        print(f"explanation={result.explanation}")
        if result.counterexample is not None:
            print(f"counterexample={result.counterexample}")
    return 0
