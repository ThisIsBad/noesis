"""Live LLM evaluation script.

Takes a JSON file of LLM answers and checks them against the verifier.
Produces a detailed comparison report.

Internal module — not part of the public API (Tier 3).
"""

from __future__ import annotations

__all__ = ["evaluate"]

import json
import sys
from pathlib import Path
from typing import Any

from logos.loader import load_problems, parse_problem
from logos.verifier import PropositionalVerifier
from logos.analyzer import ErrorAnalyzer


def evaluate(answers_path: Path) -> str:
    """Evaluate LLM answers against the deterministic verifier.

    answers_path: JSON file with format:
        {"answers": {"L1-01": {"valid": true, "reasoning": "..."}, ...}}
    """
    with open(answers_path, encoding="utf-8") as f:
        data = json.load(f)

    llm_answers = data["answers"]
    problems = load_problems()
    verifier = PropositionalVerifier()

    lines: list[str] = []
    lines.append("# 🧠 LLM vs. Gegenspieler — Live Evaluation\n")

    results_for_analyzer: list[dict[str, Any]] = []
    correct = 0
    total = 0

    for raw in problems:
        pid = raw["id"]
        if pid not in llm_answers:
            continue

        total += 1
        argument, meta = parse_problem(raw)
        verification = verifier.verify(argument)

        llm_said_valid = llm_answers[pid]["valid"]
        llm_reasoning = llm_answers[pid].get("reasoning", "")
        ground_truth = meta["expected_valid"]
        llm_correct = llm_said_valid == ground_truth

        if llm_correct:
            correct += 1

        # Collect for analyzer
        results_for_analyzer.append({
            "problem_id": pid,
            "level": meta["level"],
            "category": meta["category"],
            "expected_valid": ground_truth,
            "llm_said_valid": llm_said_valid,
        })

        # Format result
        status = "✅" if llm_correct else "❌ WRONG"
        lines.append(f"## {pid}: {meta['category']}")
        lines.append(f"**Problem**: {raw['natural_language']}\n")
        lines.append("| | LLM | Verifier | Ground Truth |")
        lines.append("|---|---|---|---|")
        lines.append(
            f"| Valid? | {'yes' if llm_said_valid else 'no'} "
            f"| {'yes' if verification.valid else 'no'} "
            f"| {'yes' if ground_truth else 'no'} |"
        )
        lines.append(f"| Status | {status} | — | — |")
        lines.append("")
        if llm_reasoning:
            lines.append(f"**LLM reasoning**: {llm_reasoning}\n")
        lines.append(f"**Verifier**: {verification}\n")
        if not llm_correct:
            lines.append("> [!CAUTION]")
            lines.append(f"> LLM got this **wrong**! {meta['explanation']}\n")
        lines.append("---\n")

    # Summary
    accuracy = correct / total if total > 0 else 0
    summary = [
        "\n# Summary\n",
        f"**Accuracy: {accuracy:.0%}** ({correct}/{total})\n",
    ]

    # Error analysis
    if total > correct:
        analyzer = ErrorAnalyzer()
        report = analyzer.analyze(results_for_analyzer)
        summary.append(report.to_markdown())

    return "\n".join(summary) + "\n\n" + "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m logos.evaluate <answers.json>")
        sys.exit(1)
    result = evaluate(Path(sys.argv[1]))
    print(result)
