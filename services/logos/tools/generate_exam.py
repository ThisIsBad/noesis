"""Generate a fresh exam via logos.generator."""

from __future__ import annotations

import argparse
from pathlib import Path

from logos.generator import GeneratorConfig, ProblemGenerator


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a fresh exam JSON")
    parser.add_argument("--count", type=int, default=10, help="Number of generated problems")
    parser.add_argument("--vars", type=int, default=4, help="Number of propositional variables")
    parser.add_argument("--premises", type=int, default=5, help="Number of premises per problem")
    parser.add_argument("--depth", type=int, default=2, help="Maximum expression nesting depth")
    parser.add_argument("--seed", type=int, default=None, help="Optional RNG seed")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/exam_fresh_001.json"),
        help="Output path for exam JSON",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config = GeneratorConfig(
        num_variables=args.vars,
        num_premises=args.premises,
        max_depth=args.depth,
        seed=args.seed,
    )
    generator = ProblemGenerator(config)
    exam = generator.generate_exam(args.count, output_path=args.output)

    print(f"Exam ID: {exam['exam_id']}")
    print(f"Generated: {exam['generated_at']}")
    print(f"Problems: {len(exam['problems'])}")
    print(f"Output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
