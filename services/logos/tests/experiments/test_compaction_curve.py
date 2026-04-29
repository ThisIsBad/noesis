"""Stage 4 experiment: compaction curve across difficulty levels."""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

import pytest
import z3

from logos import CertificateStore, certify
from logos.generator import EASY, EXTREME, HARD, MEDIUM, GeneratorConfig, ProblemGenerator
from logos.models import Connective, LogicalExpression, Proposition
from logos.parser import parse_argument, parse_expression
from logos.verifier import PropositionalVerifier


RESULTS_DIR = Path("results")
CURVE_PATH = RESULTS_DIR / "experiment_compaction_curve.json"
TIME_BUDGET_SECONDS = 120.0


class TimeBudgetExceeded(RuntimeError):
    """Raised when one difficulty level exceeds the allowed wall-time budget."""


def _normalize_claim_text(claim: str) -> str:
    return (
        claim.replace("¬", "~")
        .replace("∧", " & ")
        .replace("∨", " | ")
        .replace("→", " -> ")
        .replace("↔", " <-> ")
        .replace("⊢", " |-")
        .replace("∴", "|- ")
    )


def _expression_to_ascii(expr: Proposition | LogicalExpression) -> str:
    if isinstance(expr, Proposition):
        return expr.label
    if expr.connective is Connective.NOT:
        return f"~({_expression_to_ascii(expr.left)})"
    if expr.right is None:
        raise AssertionError("Binary expression requires right operand")
    left = _expression_to_ascii(expr.left)
    right = _expression_to_ascii(expr.right)
    if expr.connective is Connective.AND:
        return f"({left} & {right})"
    if expr.connective is Connective.OR:
        return f"({left} | {right})"
    if expr.connective is Connective.IMPLIES:
        return f"({left} -> {right})"
    if expr.connective is Connective.IFF:
        return f"({left} <-> {right})"
    raise AssertionError(f"Unsupported connective {expr.connective}")


def _extract_conclusion_text(claim: str) -> str:
    return _expression_to_ascii(parse_argument(claim).conclusion)


def check_entailment(premises_conclusions: list[str], target_conclusion: str) -> bool:
    """Check if a target conclusion is entailed by the given claim strings using Z3."""
    verifier = PropositionalVerifier()
    source_conclusions = [parse_argument(claim).conclusion for claim in premises_conclusions]
    target_expr = parse_expression(target_conclusion)

    atoms: set[str] = set()
    for conclusion in source_conclusions:
        verifier._collect_atoms_from_expr(conclusion, atoms)
    verifier._collect_atoms_from_expr(target_expr, atoms)

    z3_vars = {label: z3.Bool(label) for label in sorted(atoms)}
    solver = z3.Solver()
    for conclusion in source_conclusions:
        solver.add(verifier._to_z3(conclusion, z3_vars))
    solver.add(z3.Not(verifier._to_z3(target_expr, z3_vars)))
    return solver.check() == z3.unsat


def _write_curve_level(result: dict[str, object]) -> None:
    existing: dict[str, object]
    if CURVE_PATH.exists():
        existing = json.loads(CURVE_PATH.read_text(encoding="utf-8"))
        if not isinstance(existing, dict):
            raise AssertionError("Existing compaction curve result must be a JSON object")
    else:
        existing = {"experiment": "compaction_curve", "levels": []}

    levels = existing.get("levels", [])
    if not isinstance(levels, list):
        raise AssertionError("Compaction curve result levels must be a list")

    filtered = [
        level for level in levels if isinstance(level, dict) and level.get("difficulty") != result["difficulty"]
    ]
    filtered.append(result)
    filtered.sort(key=lambda level: ["EASY", "MEDIUM", "HARD", "EXTREME"].index(str(level["difficulty"])))

    payload = {"experiment": "compaction_curve", "levels": filtered}
    CURVE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _compaction_run(
    *,
    difficulty: str,
    config: GeneratorConfig,
    generated_count: int,
    timed_out: bool,
) -> dict[str, object]:
    generator = ProblemGenerator(
        GeneratorConfig(
            num_variables=config.num_variables,
            num_premises=config.num_premises,
            max_depth=config.max_depth,
            valid_probability=0.75,
            seed=79,
        )
    )
    store = CertificateStore()
    start = perf_counter()
    entailment_checks = 0
    entailments_found = 0

    valid_claims: list[str] = []
    for item in generator.generate_batch(generated_count):
        claim = _normalize_claim_text(str(item["formal"]))
        certificate = certify(claim)
        if not certificate.verified:
            continue
        valid_claims.append(claim)
        store.store(certificate, tags={"experiment": "compaction_curve", "difficulty": difficulty})

    compacted_claims = [
        str(entry.certificate.claim)
        for entry in store.query(limit=generated_count + 50)
        if isinstance(entry.certificate.claim, str)
    ]
    original_claims = list(compacted_claims)

    for target_claim in list(original_claims):
        if perf_counter() - start > TIME_BUDGET_SECONDS:
            raise TimeBudgetExceeded(difficulty)
        remaining = list(compacted_claims)
        remaining.remove(target_claim)
        if not remaining:
            continue
        entailment_checks += 1
        if check_entailment(remaining, _extract_conclusion_text(target_claim)):
            compacted_claims.remove(target_claim)
            entailments_found += 1

    verification_passed = True
    for claim in original_claims:
        if perf_counter() - start > TIME_BUDGET_SECONDS:
            raise TimeBudgetExceeded(difficulty)
        entailment_checks += 1
        if not check_entailment(compacted_claims, _extract_conclusion_text(claim)):
            verification_passed = False
            break

    wall_time = perf_counter() - start
    return {
        "difficulty": difficulty,
        "num_variables": config.num_variables,
        "num_premises": config.num_premises,
        "max_depth": config.max_depth,
        "generated": generated_count,
        "valid_count": len(original_claims),
        "compacted_count": len(compacted_claims),
        "compaction_ratio": round(len(compacted_claims) / len(original_claims), 6) if original_claims else 1.0,
        "entailment_checks": entailment_checks,
        "entailments_found": entailments_found,
        "verification_passed": verification_passed,
        "wall_time_seconds": round(wall_time, 6),
        "timed_out": timed_out,
    }


def _run_level(difficulty: str, config: GeneratorConfig) -> dict[str, object]:
    try:
        return _compaction_run(difficulty=difficulty, config=config, generated_count=100, timed_out=False)
    except TimeBudgetExceeded:
        return _compaction_run(difficulty=difficulty, config=config, generated_count=50, timed_out=True)


@pytest.mark.timeout(600)
@pytest.mark.parametrize(
    ("difficulty", "config"),
    [("EASY", EASY), ("MEDIUM", MEDIUM), ("HARD", HARD), ("EXTREME", EXTREME)],
)
def test_compaction_curve_across_difficulty_levels(difficulty: str, config: GeneratorConfig) -> None:
    result = _run_level(difficulty, config)
    _write_curve_level(result)

    assert isinstance(result["compacted_count"], int)
    assert isinstance(result["valid_count"], int)
    assert isinstance(result["wall_time_seconds"], float)
    assert result["compacted_count"] <= result["valid_count"]
    assert result["verification_passed"] is True
    if not result["timed_out"]:
        assert result["wall_time_seconds"] < TIME_BUDGET_SECONDS
