"""Stage 4 experiment: context-aware retrieval with Z3 relevance filtering."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from time import perf_counter

import z3

from logos import CertificateStore, certify
from logos.generator import GeneratorConfig, MEDIUM, ProblemGenerator
from logos.models import Connective, LogicalExpression, Proposition
from logos.parser import parse_argument
from logos.verifier import PropositionalVerifier


RESULTS_DIR = Path("results")
RESULT_PATH = RESULTS_DIR / "experiment_context_retrieval.json"
TIME_BUDGET_SECONDS = 120.0


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


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


def is_consistent(stored_conclusion: str, query_premises: list[str]) -> bool:
    """Check if stored_conclusion is satisfiable together with query_premises."""
    verifier = PropositionalVerifier()
    premise_exprs = [
        _expression_to_ascii(parse_argument(f"{premise} |- {premise}").conclusion)
        for premise in query_premises
    ]
    stored_expr = parse_argument(f"{stored_conclusion} |- {stored_conclusion}").conclusion

    atoms: set[str] = set()
    parsed_premises = [parse_argument(f"{premise} |- {premise}").conclusion for premise in premise_exprs]
    for premise in parsed_premises:
        verifier._collect_atoms_from_expr(premise, atoms)
    verifier._collect_atoms_from_expr(stored_expr, atoms)
    z3_vars = {label: z3.Bool(label) for label in sorted(atoms)}

    solver = z3.Solver()
    for premise in parsed_premises:
        solver.add(verifier._to_z3(premise, z3_vars))
    solver.add(verifier._to_z3(stored_expr, z3_vars))
    return solver.check() == z3.sat


def is_applicable(stored_conclusion: str, query_premises: list[str], query_conclusion: str) -> bool:
    """Check if stored_conclusion plus query_premises entails query_conclusion."""
    verifier = PropositionalVerifier()
    parsed_premises = [parse_argument(f"{premise} |- {premise}").conclusion for premise in query_premises]
    stored_expr = parse_argument(f"{stored_conclusion} |- {stored_conclusion}").conclusion
    target_expr = parse_argument(f"{query_conclusion} |- {query_conclusion}").conclusion

    atoms: set[str] = set()
    for premise in parsed_premises:
        verifier._collect_atoms_from_expr(premise, atoms)
    verifier._collect_atoms_from_expr(stored_expr, atoms)
    verifier._collect_atoms_from_expr(target_expr, atoms)
    z3_vars = {label: z3.Bool(label) for label in sorted(atoms)}

    solver = z3.Solver()
    for premise in parsed_premises:
        solver.add(verifier._to_z3(premise, z3_vars))
    stored_z3 = verifier._to_z3(stored_expr, z3_vars)
    target_z3 = verifier._to_z3(target_expr, z3_vars)
    solver.add(z3.Not(z3.Implies(z3.And(*(list(solver.assertions()) + [stored_z3])), target_z3)))
    return solver.check() == z3.unsat


def _generate_claims(*, seed: int, count: int) -> list[str]:
    generator = ProblemGenerator(
        GeneratorConfig(
            num_variables=MEDIUM.num_variables,
            num_premises=MEDIUM.num_premises,
            max_depth=MEDIUM.max_depth,
            valid_probability=0.75,
            seed=seed,
        )
    )
    claims: list[str] = []
    for item in generator.generate_batch(count):
        claim = _normalize_claim_text(str(item["formal"]))
        certificate = certify(claim)
        if certificate.verified:
            claims.append(claim)
    return claims


def test_context_aware_retrieval_with_z3_filters() -> None:
    start = perf_counter()
    store = CertificateStore()

    knowledge_claims = _generate_claims(seed=80, count=100)
    for claim in knowledge_claims:
        store.store(certify(claim), tags={"role": "knowledge_base"})

    query_claims = _generate_claims(seed=8080, count=20)
    query_claims = query_claims[:20]

    entries = store.query(tags={"role": "knowledge_base"}, limit=500)
    stored_conclusions = [
        _expression_to_ascii(parse_argument(str(entry.certificate.claim)).conclusion)
        for entry in entries
        if isinstance(entry.certificate.claim, str)
    ]

    query_results: list[dict[str, object]] = []
    consistency_reductions: list[float] = []
    applicability_precisions: list[float] = []
    consistency_times: list[float] = []
    applicability_times: list[float] = []

    for index, query_claim in enumerate(query_claims):
        query_argument = parse_argument(query_claim)
        query_premises = [_expression_to_ascii(premise) for premise in query_argument.premises]
        query_conclusion = _expression_to_ascii(query_argument.conclusion)

        consistency_start = perf_counter()
        consistent = [
            conclusion
            for conclusion in stored_conclusions
            if is_consistent(conclusion, query_premises)
        ]
        consistency_time = perf_counter() - consistency_start

        applicability_start = perf_counter()
        applicable = [
            conclusion
            for conclusion in consistent
            if is_applicable(conclusion, query_premises, query_conclusion)
        ]
        applicability_time = perf_counter() - applicability_start

        unfiltered_count = len(stored_conclusions)
        consistent_count = len(consistent)
        applicable_count = len(applicable)
        consistency_reduction = 1.0 - (consistent_count / unfiltered_count) if unfiltered_count else 0.0
        applicability_precision = applicable_count / consistent_count if consistent_count else 0.0

        assert consistent_count <= unfiltered_count
        assert applicable_count <= consistent_count
        assert consistency_reduction >= 0.0
        assert 0.0 <= applicability_precision <= 1.0

        consistency_reductions.append(consistency_reduction)
        applicability_precisions.append(applicability_precision)
        consistency_times.append(consistency_time)
        applicability_times.append(applicability_time)

        query_results.append(
            {
                "query_index": index,
                "query_claim": query_claim,
                "unfiltered_count": unfiltered_count,
                "consistent_count": consistent_count,
                "applicable_count": applicable_count,
                "consistency_reduction": round(consistency_reduction, 6),
                "applicability_precision": round(applicability_precision, 6),
                "consistency_check_seconds": round(consistency_time, 6),
                "applicability_check_seconds": round(applicability_time, 6),
            }
        )

    total_wall_time = perf_counter() - start
    assert total_wall_time < TIME_BUDGET_SECONDS

    payload = {
        "experiment": "context_retrieval",
        "knowledge_base_size": len(stored_conclusions),
        "query_count": len(query_results),
        "queries": query_results,
        "aggregates": {
            "mean_consistency_reduction": round(mean(consistency_reductions), 6) if consistency_reductions else 0.0,
            "mean_applicability_precision": (
                round(mean(applicability_precisions), 6) if applicability_precisions else 0.0
            ),
            "mean_consistency_check_seconds": round(mean(consistency_times), 6) if consistency_times else 0.0,
            "mean_applicability_check_seconds": round(mean(applicability_times), 6) if applicability_times else 0.0,
            "total_wall_time_seconds": round(total_wall_time, 6),
        },
    }
    _write_json(RESULT_PATH, payload)
