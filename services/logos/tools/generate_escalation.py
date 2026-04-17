"""Generate escalation-round exams via logos.generator presets."""

from __future__ import annotations

import argparse
from pathlib import Path

from logos.generator import GeneratorConfig, ProblemGenerator


LEVELS: dict[str, GeneratorConfig] = {
    "round1": GeneratorConfig(num_variables=6, num_premises=7, max_depth=3),
    "round2": GeneratorConfig(num_variables=8, num_premises=9, max_depth=3),
    "round3": GeneratorConfig(num_variables=10, num_premises=12, max_depth=3),
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate escalation benchmark exam")
    parser.add_argument(
        "round",
        nargs="?",
        choices=sorted(LEVELS.keys()),
        default="round1",
        help="Escalation round preset",
    )
    parser.add_argument("--count", type=int, default=5, help="Number of generated problems")
    parser.add_argument("--seed", type=int, default=None, help="Optional RNG seed")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for exam JSON (default: results/escalation_<round>.json)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    base = LEVELS[args.round]
    config = GeneratorConfig(
        num_variables=base.num_variables,
        num_premises=base.num_premises,
        max_depth=base.max_depth,
        seed=args.seed,
    )

    output = args.output or Path(f"results/escalation_{args.round}.json")
    generator = ProblemGenerator(config)
    exam = generator.generate_exam(args.count, output_path=output)

    print(f"Round: {args.round}")
    print(f"Exam ID: {exam['exam_id']}")
    print(f"Generated: {exam['generated_at']}")
    print(f"Problems: {len(exam['problems'])}")
    print(f"Output: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
