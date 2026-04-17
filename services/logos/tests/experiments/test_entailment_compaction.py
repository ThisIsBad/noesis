"""Stage 4 experiment: proof entailment compaction via Z3."""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

import z3

from logos import CertificateStore, certify
from logos.generator import EASY, GeneratorConfig, ProblemGenerator
from logos.models import Argument, Connective, LogicalExpression, Proposition
from logos.parser import parse_argument, parse_expression
from logos.verifier import PropositionalVerifier


RESULTS_DIR = Path("results")
COMPACTION_PATH = RESULTS_DIR / "experiment_entailment_compaction.json"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


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
    source_arguments = [parse_argument(claim) for claim in premises_conclusions]
    target_expr = parse_expression(target_conclusion)

    atoms: set[str] = set()
    for argument in source_arguments:
        verifier._collect_atoms(Argument(premises=argument.premises, conclusion=argument.conclusion))
        for premise in argument.premises:
            verifier._collect_atoms_from_expr(premise, atoms)
        verifier._collect_atoms_from_expr(argument.conclusion, atoms)
    verifier._collect_atoms_from_expr(target_expr, atoms)

    z3_vars = {label: z3.Bool(label) for label in sorted(atoms)}
    solver = z3.Solver()
    for argument in source_arguments:
        for premise in argument.premises:
            solver.add(verifier._to_z3(premise, z3_vars))
        solver.add(verifier._to_z3(argument.conclusion, z3_vars))
    solver.add(z3.Not(verifier._to_z3(target_expr, z3_vars)))
    return solver.check() == z3.unsat


def _build_manual_claims() -> dict[str, str]:
    return {
        "cert1": "P -> Q, P |- Q",
        "cert2": "P -> Q, Q -> R |- P -> R",
        "cert3": "P -> Q, P |- Q",
        "cert4": "P |- P",
        "cert5": "P -> Q, Q -> R, P |- R",
        "cert6": "S -> T, S |- T",
        "cert7": "U -> V, U |- V",
        "cert8": "W -> X, W |- X",
        "cert9": "Y -> Z, Y |- Z",
        "cert10": "A -> B, A |- B",
    }


def _compute_redundancies(claims_by_name: dict[str, str]) -> tuple[dict[str, list[str]], set[str], int]:
    redundancies: dict[str, list[str]] = {}
    entailment_checks = 0
    names = list(claims_by_name)

    for target_name in names:
        target_conclusion = _extract_conclusion_text(claims_by_name[target_name])
        evidence: list[str] = []
        for source_name in names:
            if source_name == target_name:
                continue
            entailment_checks += 1
            if check_entailment([claims_by_name[source_name]], target_conclusion):
                evidence = [source_name]
                break
        if not evidence:
            for i, left_name in enumerate(names):
                if left_name == target_name:
                    continue
                for right_name in names[i + 1 :]:
                    if right_name == target_name or right_name == left_name:
                        continue
                    entailment_checks += 1
                    if check_entailment([claims_by_name[left_name], claims_by_name[right_name]], target_conclusion):
                        evidence = [left_name, right_name]
                        break
                if evidence:
                    break
        if evidence:
            redundancies[target_name] = evidence

    redundant_names = set(redundancies)
    minimal_names = set(names) - redundant_names
    return redundancies, minimal_names, entailment_checks


def _run_random_compaction() -> dict[str, object]:
    generator = ProblemGenerator(
        GeneratorConfig(
            num_variables=EASY.num_variables,
            num_premises=EASY.num_premises,
            max_depth=EASY.max_depth,
            valid_probability=0.75,
            seed=78,
        )
    )
    store = CertificateStore()
    valid_claims: list[str] = []

    start = perf_counter()
    for item in generator.generate_batch(100):
        claim = str(item["formal"])
        claim = (
            claim.replace("¬", "~")
            .replace("∧", " & ")
            .replace("∨", " | ")
            .replace("→", " -> ")
            .replace("↔", " <-> ")
            .replace("⊢", " |-")
        )
        certificate = certify(claim)
        if not certificate.verified:
            continue
        valid_claims.append(claim)
        store.store(certificate, tags={"experiment": "entailment_compaction"})

    unique_entries = store.query(limit=1000)
    unique_claims = [
        str(entry.certificate.claim)
        for entry in unique_entries
        if isinstance(entry.certificate.claim, str)
    ]

    removed_claims: list[str] = []
    entailments_found = 0
    entailment_checks = 0
    compacted_claims = list(unique_claims)
    for target_claim in unique_claims:
        remaining = [claim for claim in compacted_claims if claim != target_claim]
        if not remaining:
            continue
        entailment_checks += len(remaining)
        if check_entailment(remaining, _extract_conclusion_text(target_claim)):
            compacted_claims.remove(target_claim)
            removed_claims.append(target_claim)
            entailments_found += 1

    verification_passed = all(
        check_entailment(compacted_claims, _extract_conclusion_text(claim))
        for claim in unique_claims
    )
    wall_time = perf_counter() - start
    result = {
        "experiment": "entailment_compaction",
        "original_count": 100,
        "valid_count": len(unique_claims),
        "compacted_count": len(compacted_claims),
        "compaction_ratio": round(len(compacted_claims) / len(unique_claims), 6) if unique_claims else 1.0,
        "entailment_checks_performed": entailment_checks,
        "entailments_found": entailments_found,
        "verification_passed": verification_passed,
        "wall_time_seconds": round(wall_time, 6),
    }
    _write_json(COMPACTION_PATH, result)
    return {
        "store": store,
        "unique_claims": unique_claims,
        "compacted_claims": compacted_claims,
        "removed_claims": removed_claims,
        "result": result,
    }


def test_entailment_compaction_directed_redundancy_detection() -> None:
    store = CertificateStore()
    claims = _build_manual_claims()
    certificates = {name: certify(claim) for name, claim in claims.items() if name != "cert3"}
    certificates["cert3"] = certificates["cert1"]
    store_ids = {
        name: store.store(certificate, tags={"experiment": "manual", "name": name})
        for name, certificate in certificates.items()
    }
    unique_claims = {name: claim for name, claim in claims.items() if name != "cert3"}
    redundancies, minimal_names, _ = _compute_redundancies(unique_claims)

    assert store_ids["cert1"] == store_ids["cert3"]
    assert redundancies["cert4"]
    assert redundancies["cert5"] == ["cert1", "cert2"]
    for name in ("cert6", "cert7", "cert8", "cert9", "cert10"):
        assert name not in redundancies
    assert "cert4" not in minimal_names
    assert "cert5" not in minimal_names


def test_entailment_compaction_random_compaction() -> None:
    outcome = _run_random_compaction()
    result = outcome["result"]

    assert isinstance(result, dict)
    assert result["compacted_count"] <= result["valid_count"]
    assert result["verification_passed"] is True


def test_entailment_compaction_preserves_all_original_conclusions() -> None:
    outcome = _run_random_compaction()
    unique_claims = outcome["unique_claims"]
    compacted_claims = outcome["compacted_claims"]

    assert all(check_entailment(compacted_claims, _extract_conclusion_text(claim)) for claim in unique_claims)
