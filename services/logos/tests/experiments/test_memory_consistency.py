"""Stage 4 experiment: memory consistency stress tests."""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

from logos import BeliefEdgeType, BeliefGraph, CertificateStore, certify, verify
from logos.generator import MEDIUM, GeneratorConfig, ProblemGenerator


RESULTS_DIR = Path("results")
SCALE_PATH = RESULTS_DIR / "experiment_memory_scale.json"
CONTRADICTION_PATH = RESULTS_DIR / "experiment_contradiction_detection.json"
MIXED_PATH = RESULTS_DIR / "experiment_mixed_accumulation.json"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _generator(*, seed: int, valid_probability: float = 0.5) -> ProblemGenerator:
    return ProblemGenerator(
        GeneratorConfig(
            num_variables=MEDIUM.num_variables,
            num_premises=MEDIUM.num_premises,
            max_depth=MEDIUM.max_depth,
            valid_probability=valid_probability,
            seed=seed,
        )
    )


def _normalize_argument_text(argument: str) -> str:
    return (
        argument.replace("¬", "~")
        .replace("∧", " & ")
        .replace("∨", " | ")
        .replace("→", " -> ")
        .replace("↔", " <-> ")
        .replace("⊢", " |-")
        .replace("∴", "|- ")
    )


def _collect_arguments(count: int, *, seed: int, want_valid: bool | None = None) -> list[str]:
    generator = _generator(seed=seed, valid_probability=0.5 if want_valid is None else (1.0 if want_valid else 0.0))
    arguments: list[str] = []
    index = 0
    while len(arguments) < count:
        batch = generator.generate_batch(25)
        for item in batch:
            formal = _normalize_argument_text(str(item["formal"]))
            if want_valid is not None and verify(formal).valid is not want_valid:
                continue
            arguments.append(formal)
            if len(arguments) == count:
                break
        index += 1
        if index > 1000:
            raise AssertionError("ProblemGenerator did not yield enough matching arguments")
    return arguments


def test_memory_consistency_scale() -> None:
    store = CertificateStore()
    arguments = _collect_arguments(500, seed=77)
    checkpoint_records: list[dict[str, object]] = []
    store_ids: list[str] = []

    start = perf_counter()
    for index, argument in enumerate(arguments, start=1):
        store_id = store.store(certify(argument), tags={"experiment": "memory_scale", "index": str(index)})
        store_ids.append(store_id)
        if index % 50 == 0:
            checkpoint_records.append(
                {
                    "at_count": index,
                    "elapsed_seconds": round(perf_counter() - start, 6),
                    "stats": store.stats().to_dict(),
                }
            )

    wall_time = perf_counter() - start
    unique_ids = sorted(set(store_ids))
    stats = store.stats()

    assert stats.total == len(unique_ids)
    assert stats.total <= 500
    assert all(store.get(store_id) is not None for store_id in unique_ids)
    assert wall_time < 30.0

    _write_json(
        SCALE_PATH,
        {
            "experiment": "memory_consistency_scale",
            "certificate_count": 500,
            "unique_count": len(unique_ids),
            "wall_time_seconds": round(wall_time, 6),
            "checkpoints": checkpoint_records,
        },
    )


def test_memory_consistency_contradiction_injection() -> None:
    store = CertificateStore()
    graph = BeliefGraph()
    arguments = _collect_arguments(20, seed=78, want_valid=True)

    base_ids: list[str] = []
    for index, argument in enumerate(arguments):
        certificate = certify(argument)
        store.store(certificate, tags={"experiment": "contradictions", "kind": "base"})
        belief_id = f"base-{index}"
        graph.add_belief(belief_id, statement=f"x{index} > 0")
        base_ids.append(belief_id)

    injected_pairs: set[tuple[str, str]] = set()
    explanations_with_paths = 0
    for index, base_id in enumerate(base_ids[:5]):
        contradiction_id = f"contradiction-{index}"
        graph.add_belief(contradiction_id, statement=f"x{index} < 0")
        graph.add_edge(base_id, contradiction_id, BeliefEdgeType.CONTRADICTS)
        pair = tuple(sorted((base_id, contradiction_id)))
        injected_pairs.add((pair[0], pair[1]))

    contradictions = set(graph.detect_contradictions_z3(variables={f"x{i}": "Int" for i in range(20)}))
    frontier = set(graph.contradiction_frontier())
    assert frontier == contradictions

    for left_id, right_id in sorted(frontier):
        explanation = graph.explain_contradiction(left_id, right_id)
        if explanation.left_support_path and explanation.right_support_path:
            explanations_with_paths += 1

    false_positives = len(frontier - injected_pairs)
    false_negatives = len(injected_pairs - frontier)

    assert len(frontier) == 5
    assert explanations_with_paths == 5
    assert false_positives == 0
    assert false_negatives == 0

    _write_json(
        CONTRADICTION_PATH,
        {
            "experiment": "memory_consistency_contradictions",
            "total_beliefs": len(graph.beliefs()),
            "injected_contradictions": 5,
            "detected_contradictions": len(frontier),
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "explanations_with_paths": explanations_with_paths,
        },
    )


def test_memory_consistency_mixed_accumulation() -> None:
    store = CertificateStore()
    valid_arguments = _collect_arguments(100, seed=79, want_valid=True)
    invalid_arguments = _collect_arguments(100, seed=80, want_valid=False)

    for index in range(100):
        valid_cert = certify(valid_arguments[index])
        invalid_cert = certify(invalid_arguments[index])
        store.store(valid_cert, tags={"experiment": "mixed", "kind": "valid", "index": str(index)})
        store.store(invalid_cert, tags={"experiment": "mixed", "kind": "invalid", "index": str(index)})

    valid_start = perf_counter()
    valid_entries = store.query(verified=True, limit=500)
    valid_query_time = perf_counter() - valid_start

    invalid_start = perf_counter()
    invalid_entries = store.query(verified=False, limit=500)
    invalid_query_time = perf_counter() - invalid_start

    expected_valid = sum(1 for argument in valid_arguments if certify(argument).verified)
    expected_invalid = sum(1 for argument in invalid_arguments if not certify(argument).verified)

    assert len(valid_entries) == expected_valid
    assert len(invalid_entries) == expected_invalid

    _write_json(
        MIXED_PATH,
        {
            "experiment": "memory_consistency_mixed_accumulation",
            "certificate_count": 200,
            "expected_valid": expected_valid,
            "expected_invalid": expected_invalid,
            "actual_valid": len(valid_entries),
            "actual_invalid": len(invalid_entries),
            "valid_query_seconds": round(valid_query_time, 6),
            "invalid_query_seconds": round(invalid_query_time, 6),
        },
    )
