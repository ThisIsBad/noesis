"""Check benchmark answer files against their answer keys.

Supports:
- exam:       results/exam_fresh_001.json + results/llm_answers_fresh.json
- hardmode:   results/<name>.json + results/<name>_answers.json
- escalation: results/escalation_<name>.json + results/escalation_<name>_answers.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _compute_paths(kind: str, name: str) -> tuple[Path, Path]:
    results_dir = Path("results")

    if kind == "exam":
        exam_name = name if name else "exam_fresh_001"
        answers_name = "llm_answers_fresh"
        return results_dir / f"{exam_name}.json", results_dir / f"{answers_name}.json"

    if kind == "hardmode":
        round_name = name if name else "hardmode_8v_8p"
        return results_dir / f"{round_name}.json", results_dir / f"{round_name}_answers.json"

    round_name = name if name else "round1"
    return (
        results_dir / f"escalation_{round_name}.json",
        results_dir / f"escalation_{round_name}_answers.json",
    )


def _print_score(exam_data: dict, answer_data: dict) -> int:
    answers = answer_data.get("answers", {})
    key = exam_data.get("answer_key", {})

    correct = 0
    total = 0
    wrong: list[str] = []
    missing: list[str] = []

    for problem_id in sorted(key.keys()):
        total += 1
        truth = key[problem_id]["valid"]
        llm_ans = answers.get(problem_id, {}).get("valid")

        if llm_ans is None:
            print(f"MISS         {problem_id} | no answer")
            missing.append(problem_id)
            continue

        ok = llm_ans == truth
        if ok:
            correct += 1
        else:
            wrong.append(problem_id)

        status = "OK" if ok else "WRONG"
        print(
            f"{status:12s} {problem_id} | "
            f"LLM={'valid' if llm_ans else 'invalid':7s} "
            f"truth={'valid' if truth else 'invalid':7s}"
        )

    percent = (100 * correct // total) if total else 0
    print(f"\nScore: {correct}/{total} ({percent}%)")

    if wrong:
        print("Failed:", ", ".join(wrong))
    if missing:
        print("Missing:", ", ".join(missing))

    return 0 if (not wrong and not missing) else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check benchmark run results")
    parser.add_argument(
        "kind",
        nargs="?",
        choices=["exam", "hardmode", "escalation"],
        default="exam",
        help="Result family to check (ignored when --benchmarks and --answers are provided)",
    )
    parser.add_argument(
        "name",
        nargs="?",
        default="",
        help="Optional run name (e.g. hardmode_10v_10p or round2)",
    )
    parser.add_argument(
        "--benchmarks",
        type=Path,
        help="Explicit benchmark result file path (overrides kind/name path resolution)",
    )
    parser.add_argument(
        "--answers",
        type=Path,
        help="Explicit answers file path (overrides kind/name path resolution)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if args.benchmarks or args.answers:
        if not (args.benchmarks and args.answers):
            raise ValueError("Provide both --benchmarks and --answers together")
        exam_path, answer_path = args.benchmarks, args.answers
    else:
        exam_path, answer_path = _compute_paths(args.kind, args.name)

    if not exam_path.exists():
        raise FileNotFoundError(f"Exam file not found: {exam_path}")
    if not answer_path.exists():
        raise FileNotFoundError(f"Answer file not found: {answer_path}")

    exam_data = _load_json(exam_path)
    answer_data = _load_json(answer_path)
    return _print_score(exam_data, answer_data)


if __name__ == "__main__":
    raise SystemExit(main())
