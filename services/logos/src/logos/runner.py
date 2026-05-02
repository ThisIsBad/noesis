"""Benchmark runner — verifies all problems and collects results.

Internal module — not part of the public API (Tier 3).
"""

from __future__ import annotations

__all__ = ["BenchmarkRunner", "ProblemResult", "format_report"]

from dataclasses import dataclass, field

from logos.loader import load_problems, parse_problem
from logos.models import VerificationResult
from logos.verifier import PropositionalVerifier


@dataclass
class ProblemResult:
    """Result of verifying a single benchmark problem."""

    problem_id: str
    level: int | str
    category: str
    natural_language: str
    expected_valid: bool
    actual_valid: bool
    verification: VerificationResult
    verifier_correct: bool = field(init=False)

    def __post_init__(self) -> None:
        self.verifier_correct = self.expected_valid == self.actual_valid


class BenchmarkRunner:
    """Runs all benchmark problems through the verifier.

    This validates that the *verifier itself* is correct — it must agree
    with every expected_valid flag in the benchmark suite.
    """

    def __init__(self) -> None:
        self.verifier = PropositionalVerifier()

    def run_all(self) -> list[ProblemResult]:
        """Run every benchmark problem and return results."""
        raw_problems = load_problems()
        results: list[ProblemResult] = []

        for raw in raw_problems:
            argument, meta = parse_problem(raw)
            verification = self.verifier.verify(argument)

            result = ProblemResult(
                problem_id=meta["id"],
                level=meta["level"],
                category=meta["category"],
                natural_language=meta.get("natural_language", argument.natural_language),
                expected_valid=meta["expected_valid"],
                actual_valid=verification.valid,
                verification=verification,
            )
            results.append(result)

        return results

    def run_and_report(self) -> str:
        """Run all benchmarks and return a markdown report."""
        results = self.run_all()
        return format_report(results)


def format_report(results: list[ProblemResult]) -> str:
    """Format results as a markdown report."""
    lines: list[str] = []
    lines.append("# LogicBrain Verifier Benchmark Report\n")

    # Summary
    total = len(results)
    correct = sum(1 for r in results if r.verifier_correct)
    lines.append(f"**Overall: {correct}/{total} correct** ({'✅ ALL PASS' if correct == total else '❌ FAILURES'})\n")

    # Group by level
    levels: dict[str, list[ProblemResult]] = {}
    for r in results:
        key = str(r.level)
        levels.setdefault(key, []).append(r)

    for level_key in sorted(levels.keys()):
        level_results = levels[level_key]
        level_correct = sum(1 for r in level_results if r.verifier_correct)
        level_label = f"Level {level_key}" if level_key.isdigit() else level_key.title()
        lines.append(f"\n## {level_label} ({level_correct}/{len(level_results)})\n")
        lines.append("| ID | Category | Expected | Actual | Status | Rule |")
        lines.append("|---|---|---|---|---|---|")

        for r in level_results:
            status = "✅" if r.verifier_correct else "❌ MISMATCH"
            expected = "valid" if r.expected_valid else "invalid"
            actual = "valid" if r.actual_valid else "invalid"
            lines.append(
                f"| {r.problem_id} | {r.category} | {expected} | {actual} | {status} | {r.verification.rule} |"
            )

    # Failures detail
    failures = [r for r in results if not r.verifier_correct]
    if failures:
        lines.append("\n## ❌ Failure Details\n")
        for r in failures:
            lines.append(f"### {r.problem_id} ({r.category})")
            lines.append(f"- **Natural language**: {r.natural_language}")
            lines.append(f"- **Expected**: {'valid' if r.expected_valid else 'invalid'}")
            lines.append(f"- **Got**: {'valid' if r.actual_valid else 'invalid'}")
            lines.append(f"- **Explanation**: {r.verification.explanation}")
            if r.verification.counterexample:
                lines.append(f"- **Counterexample**: {r.verification.counterexample}")
            lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    runner = BenchmarkRunner()
    print(runner.run_and_report())
