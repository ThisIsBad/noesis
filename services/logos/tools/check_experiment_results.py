"""Check experiment result files for Stage 4 validation runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


RESULTS_DIR = Path("results")


def _load_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"Experiment result must be a JSON object: {path}")
    return {str(key): value for key, value in data.items()}


def _require_number(payload: dict[str, object], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, int | float):
        raise ValueError(f"Field '{key}' must be numeric")
    return float(value)


def _require_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ValueError(f"Field '{key}' must be an integer")
    return value


def _memory_consistency_paths() -> tuple[Path, Path, Path]:
    return (
        RESULTS_DIR / "experiment_memory_scale.json",
        RESULTS_DIR / "experiment_contradiction_detection.json",
        RESULTS_DIR / "experiment_mixed_accumulation.json",
    )


def _check_memory_consistency() -> int:
    scale_path, contradiction_path, mixed_path = _memory_consistency_paths()
    for path in (scale_path, contradiction_path, mixed_path):
        if not path.exists():
            raise FileNotFoundError(f"Missing experiment result file: {path}")

    scale = _load_json(scale_path)
    contradictions = _load_json(contradiction_path)
    mixed = _load_json(mixed_path)

    rows = [
        (
            "scale_wall_time<30s",
            _require_number(scale, "wall_time_seconds") < 30.0,
            f"wall_time={_require_number(scale, 'wall_time_seconds'):.3f}s",
        ),
        (
            "detected==injected",
            _require_int(contradictions, "detected_contradictions")
            == _require_int(contradictions, "injected_contradictions"),
            (
                f"detected={_require_int(contradictions, 'detected_contradictions')} "
                f"injected={_require_int(contradictions, 'injected_contradictions')}"
            ),
        ),
        (
            "false_positives==0",
            _require_int(contradictions, "false_positives") == 0,
            f"false_positives={_require_int(contradictions, 'false_positives')}",
        ),
        (
            "false_negatives==0",
            _require_int(contradictions, "false_negatives") == 0,
            f"false_negatives={_require_int(contradictions, 'false_negatives')}",
        ),
        (
            "mixed_counts_match",
            _require_int(mixed, "expected_valid") == _require_int(mixed, "actual_valid")
            and _require_int(mixed, "expected_invalid") == _require_int(mixed, "actual_invalid"),
            (
                f"valid={_require_int(mixed, 'actual_valid')}/{_require_int(mixed, 'expected_valid')} "
                f"invalid={_require_int(mixed, 'actual_invalid')}/{_require_int(mixed, 'expected_invalid')}"
            ),
        ),
    ]

    print("check                        status   details")
    print("-------------------------------------------------------------")
    failures = 0
    for name, ok, detail in rows:
        print(f"{name:28s} {'PASS' if ok else 'FAIL':6s} {detail}")
        failures += int(not ok)
    return 0 if failures == 0 else 1


def _check_entailment_compaction() -> int:
    path = RESULTS_DIR / "experiment_entailment_compaction.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing experiment result file: {path}")

    payload = _load_json(path)
    compacted_count = _require_int(payload, "compacted_count")
    original_count = _require_int(payload, "original_count")
    compaction_ratio = _require_number(payload, "compaction_ratio")
    verification_passed = payload.get("verification_passed") is True

    rows = [
        (
            "verification_passed",
            verification_passed,
            f"verification_passed={verification_passed}",
        ),
        (
            "compacted<=original",
            compacted_count <= original_count,
            f"compacted={compacted_count} original={original_count}",
        ),
        (
            "compaction_ratio",
            True,
            f"ratio={compaction_ratio:.3f}",
        ),
    ]

    print("check                        status   details")
    print("-------------------------------------------------------------")
    failures = 0
    for name, ok, detail in rows:
        print(f"{name:28s} {'PASS' if ok else 'FAIL':6s} {detail}")
        failures += int(not ok)
    return 0 if failures == 0 else 1


def _check_compaction_curve() -> int:
    path = RESULTS_DIR / "experiment_compaction_curve.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing experiment result file: {path}")

    payload = _load_json(path)
    levels = payload.get("levels")
    if not isinstance(levels, list):
        raise ValueError("Compaction curve results must contain a 'levels' list")

    print("Difficulty   Variables  Valid  Compacted  Ratio     Time")
    print("---------------------------------------------------------")
    failures = 0
    for level in levels:
        if not isinstance(level, dict):
            raise ValueError("Each compaction curve level must be an object")
        difficulty = str(level.get("difficulty"))
        variables = _require_int(level, "num_variables")
        valid_count = _require_int(level, "valid_count")
        compacted_count = _require_int(level, "compacted_count")
        ratio = _require_number(level, "compaction_ratio")
        wall_time = _require_number(level, "wall_time_seconds")
        verification_passed = level.get("verification_passed") is True
        if compacted_count > valid_count or not verification_passed:
            failures += 1
        print(
            f"{difficulty:12s}{variables:<11d}{valid_count:<7d}{compacted_count:<11d}{ratio:<10.4f}{wall_time:.1f}s"
        )
    return 0 if failures == 0 else 1


def _check_context_retrieval() -> int:
    path = RESULTS_DIR / "experiment_context_retrieval.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing experiment result file: {path}")

    payload = _load_json(path)
    knowledge_base_size = _require_int(payload, "knowledge_base_size")
    query_count = _require_int(payload, "query_count")
    queries = payload.get("queries")
    aggregates = payload.get("aggregates")
    if not isinstance(queries, list):
        raise ValueError("Context retrieval results must contain a 'queries' list")
    if not isinstance(aggregates, dict):
        raise ValueError("Context retrieval results must contain an 'aggregates' object")

    print(f"Knowledge base: {knowledge_base_size} certificates")
    print(f"Queries: {query_count}\n")
    print("Query  Unfiltered  Consistent  Applicable  Reduction  Precision")
    print("---------------------------------------------------------------")

    failures = 0
    for item in queries:
        if not isinstance(item, dict):
            raise ValueError("Each context retrieval query result must be an object")
        query_index = _require_int(item, "query_index")
        unfiltered = _require_int(item, "unfiltered_count")
        consistent = _require_int(item, "consistent_count")
        applicable = _require_int(item, "applicable_count")
        reduction = _require_number(item, "consistency_reduction")
        precision = _require_number(item, "applicability_precision")

        if consistent > unfiltered or applicable > consistent or reduction < 0.0 or not (0.0 <= precision <= 1.0):
            failures += 1

        print(
            f"{query_index:<6d} {unfiltered:<11d}{consistent:<12d}{applicable:<12d}"
            f"{reduction * 100:>7.1f}%   {precision * 100:>7.1f}%"
        )

    print("\nAggregates:")
    print(f"  Mean consistency reduction:     {_require_number(aggregates, 'mean_consistency_reduction') * 100:.1f}%")
    print(f"  Mean applicability precision:   {_require_number(aggregates, 'mean_applicability_precision') * 100:.1f}%")
    print(f"  Mean check time per query:      {_require_number(aggregates, 'mean_applicability_check_seconds'):.2f}s")

    return 0 if failures == 0 else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check experiment result files")
    parser.add_argument(
        "experiment",
        choices=["memory_consistency", "entailment_compaction", "compaction_curve", "context_retrieval"],
        help="Experiment family to validate",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.experiment == "memory_consistency":
        return _check_memory_consistency()
    if args.experiment == "entailment_compaction":
        return _check_entailment_compaction()
    if args.experiment == "compaction_curve":
        return _check_compaction_curve()
    if args.experiment == "context_retrieval":
        return _check_context_retrieval()
    raise ValueError(f"Unsupported experiment '{args.experiment}'")


if __name__ == "__main__":
    raise SystemExit(main())
