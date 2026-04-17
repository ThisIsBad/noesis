"""Generate harder benchmark exams via logos.generator."""

from __future__ import annotations

import argparse
from pathlib import Path

from logos.generator import GeneratorConfig, ProblemGenerator


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate hardmode exam JSON")
    parser.add_argument("legacy_vars", nargs="?", type=int, help="Legacy positional: vars")
    parser.add_argument("legacy_premises", nargs="?", type=int, help="Legacy positional: premises")
    parser.add_argument("legacy_count", nargs="?", type=int, help="Legacy positional: count")
    parser.add_argument("legacy_depth", nargs="?", type=int, help="Legacy positional: depth")
    parser.add_argument("--vars", type=int, default=8, help="Number of propositional variables")
    parser.add_argument("--premises", type=int, default=8, help="Number of premises per problem")
    parser.add_argument("--depth", type=int, default=3, help="Maximum expression nesting depth")
    parser.add_argument("--count", type=int, default=5, help="Number of generated problems")
    parser.add_argument("--seed", type=int, default=None, help="Optional RNG seed")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for exam JSON (default: results/hardmode_<vars>v_<premises>p.json)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    vars_count = args.legacy_vars if args.legacy_vars is not None else args.vars
    premises_count = (
        args.legacy_premises if args.legacy_premises is not None else args.premises
    )
    count = args.legacy_count if args.legacy_count is not None else args.count
    depth = args.legacy_depth if args.legacy_depth is not None else args.depth

    output = args.output or Path(f"results/hardmode_{vars_count}v_{premises_count}p.json")

    config = GeneratorConfig(
        num_variables=vars_count,
        num_premises=premises_count,
        max_depth=depth,
        seed=args.seed,
        valid_probability=0.5,
    )
    generator = ProblemGenerator(config)
    exam = generator.generate_exam(count, output_path=output)

    print(f"Exam ID: {exam['exam_id']}")
    print(f"Generated: {exam['generated_at']}")
    print(f"Problems: {len(exam['problems'])}")
    print(f"Output: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
