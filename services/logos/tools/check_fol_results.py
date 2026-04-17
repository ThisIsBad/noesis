"""Check first-order-logic benchmark answers against expected labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check FOL benchmark answers")
    parser.add_argument(
        "--benchmarks",
        type=Path,
        default=Path("benchmarks/predicate_problems.json"),
        help="Path to FOL benchmark problems JSON",
    )
    parser.add_argument(
        "--answers",
        type=Path,
        default=Path("results/predicate_answers.json"),
        help="Path to FOL answers JSON",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if not args.benchmarks.exists():
        raise FileNotFoundError(f"Benchmark file not found: {args.benchmarks}")
    if not args.answers.exists():
        raise FileNotFoundError(f"Answer file not found: {args.answers}")

    problems = _load_json(args.benchmarks).get("problems", [])
    answers = _load_json(args.answers).get("answers", {})

    total = len(problems)
    correct = 0
    missing = 0
    wrong: list[str] = []

    print(f"{'Status':12s} {'ID':8s} | LLM vs truth")
    print("-" * 56)

    for problem in problems:
        pid = problem["id"]
        truth = bool(problem["expected_valid"])
        answer = answers.get(pid)
        if answer is None:
            missing += 1
            print(f"{'MISS':12s} {pid:8s} | no answer")
            continue

        llm_ans = answer.get("valid")
        if llm_ans is None:
            missing += 1
            print(f"{'MISS':12s} {pid:8s} | missing 'valid' key")
            continue

        ok = bool(llm_ans) == truth
        if ok:
            correct += 1
            status = "OK"
        else:
            wrong.append(pid)
            status = "WRONG"

        print(
            f"{status:12s} {pid:8s} | "
            f"LLM={'valid' if llm_ans else 'invalid':7s} "
            f"truth={'valid' if truth else 'invalid':7s}"
        )

    denominator = total if total else 1
    score = (100 * correct) // denominator
    print(f"\nScore: {correct}/{total} ({score}%)")
    if missing:
        print(f"Missing: {missing}")
    if wrong:
        print("Failed:", ", ".join(wrong))

    return 0 if (correct == total and missing == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
