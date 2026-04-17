"""Error pattern analyzer for LLM logic evaluation results.

Internal module — not part of the public API (Tier 3).
"""

from __future__ import annotations

__all__ = ["AnalysisReport", "ErrorAnalyzer"]

from collections import Counter
from dataclasses import dataclass
from typing import Any


@dataclass
class AnalysisReport:
    """Aggregated analysis of LLM performance on logic benchmarks."""

    total_problems: int
    correct: int
    incorrect: int
    accuracy: float
    errors_by_category: dict[str, int]
    errors_by_level: dict[str, int]
    most_common_errors: list[tuple[str, int]]
    false_positives: int  # LLM said valid but was invalid
    false_negatives: int  # LLM said invalid but was valid

    def to_markdown(self) -> str:
        lines = [
            "# LLM Logic Evaluation — Error Analysis\n",
            f"**Accuracy: {self.accuracy:.1%}** ({self.correct}/{self.total_problems})\n",
            f"- False positives (said valid, was invalid): {self.false_positives}",
            f"- False negatives (said invalid, was valid): {self.false_negatives}\n",
        ]

        if self.errors_by_level:
            lines.append("## Errors by Difficulty Level\n")
            for level, count in sorted(self.errors_by_level.items()):
                lines.append(f"- **{level}**: {count} error(s)")
            lines.append("")

        if self.most_common_errors:
            lines.append("## Most Common Error Categories\n")
            for category, count in self.most_common_errors:
                lines.append(f"1. **{category}**: {count} error(s)")
            lines.append("")

        return "\n".join(lines)


class ErrorAnalyzer:
    """Analyzes patterns in LLM logic evaluation results.

    Input format: list of dicts with keys:
      - problem_id, level, category
      - expected_valid (bool): ground truth
      - llm_said_valid (bool): what the LLM concluded
    """

    def analyze(self, results: list[dict[str, Any]]) -> AnalysisReport:
        total = len(results)
        errors = [r for r in results if r["expected_valid"] != r["llm_said_valid"]]
        correct = total - len(errors)

        category_counter: Counter[str] = Counter()
        level_counter: Counter[str] = Counter()
        false_positives = 0
        false_negatives = 0

        for e in errors:
            category_counter[e["category"]] += 1
            level_counter[str(e["level"])] += 1
            if e["llm_said_valid"] and not e["expected_valid"]:
                false_positives += 1
            else:
                false_negatives += 1

        return AnalysisReport(
            total_problems=total,
            correct=correct,
            incorrect=len(errors),
            accuracy=correct / total if total > 0 else 0.0,
            errors_by_category=dict(category_counter),
            errors_by_level=dict(level_counter),
            most_common_errors=category_counter.most_common(),
            false_positives=false_positives,
            false_negatives=false_negatives,
        )
