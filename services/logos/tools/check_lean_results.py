"""Check Lean benchmark answers against the Lean compiler."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from logos.lean_verifier import LeanVerifier


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Lean benchmark answers")
    parser.add_argument(
        "--benchmarks",
        type=Path,
        default=Path("benchmarks/lean_problems.json"),
        help="Path to Lean benchmark problems JSON",
    )
    parser.add_argument(
        "--answers",
        type=Path,
        default=Path("results/lean_answers.json"),
        help="Path to Lean answers JSON",
    )
    parser.add_argument(
        "--lean-bin",
        default="lean",
        help="Lean executable path (default: lean from PATH)",
    )
    return parser.parse_args()


def _safe_terminal_text(text: str) -> str:
    return text.encode("ascii", errors="replace").decode("ascii")


def main() -> int:
    args = _parse_args()

    if not args.benchmarks.exists():
        raise FileNotFoundError(f"Benchmark file not found: {args.benchmarks}")
    if not args.answers.exists():
        raise FileNotFoundError(f"Answer file not found: {args.answers}")

    benchmarks = _load_json(args.benchmarks).get("problems", [])
    answers = _load_json(args.answers).get("answers", {})
    verifier = LeanVerifier(args.lean_bin)

    total = len(benchmarks)
    checked = 0
    correct = 0
    missing = 0
    failed: list[str] = []

    print(f"{'Status':12s} {'ID':8s} | Tactic")
    print("-" * 72)

    for problem in benchmarks:
        pid = problem["id"]
        answer = answers.get(pid)
        if answer is None:
            missing += 1
            print(f"{'MISS':12s} {pid:8s} | no answer")
            continue

        tactic = answer.get("tactic_proof", "")
        tactic_for_print = _safe_terminal_text(tactic)
        checked += 1

        result = verifier.verify(problem["lean_header"], tactic)
        if result.valid:
            correct += 1
            print(f"{'OK':12s} {pid:8s} | {tactic_for_print}")
        else:
            failed.append(pid)
            print(f"{'WRONG':12s} {pid:8s} | {tactic_for_print}")
            if result.error:
                print(f"  error: {result.error}")

    denominator = total if total else 1
    score = (100 * correct) // denominator
    print(f"\nScore: {correct}/{total} ({score}%)")
    if missing:
        print(f"Missing: {missing}")
    if failed:
        print("Failed:", ", ".join(failed))

    return 0 if (correct == total and missing == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
