"""Fresh logic problem generator — creates unique problems at runtime.

These problems are GUARANTEED to not be in any LLM's training data because
they are randomly generated at evaluation time. The Z3 verifier determines
the ground truth, making the evaluation fully deterministic and trustworthy.

Design principle: The LLM cannot cheat. It must reason.

``ProblemGenerator`` and ``GeneratorConfig`` are exported from the public
API (Tier 2 — Provisional). Difficulty presets (``EASY``, ``MEDIUM``,
``HARD``, ``EXTREME``) are available as module-level constants.
"""

from __future__ import annotations

__all__ = ["ProblemGenerator", "GeneratorConfig", "EASY", "MEDIUM", "HARD", "EXTREME"]

import hashlib
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from logos.models import (
    Argument,
    Connective,
    LogicalExpression,
    Proposition,
)
from logos.verifier import PropositionalVerifier


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class GeneratorConfig:
    """Controls difficulty of generated problems."""

    # Number of atomic variables (more = harder)
    num_variables: int = 4

    # Number of premises (more = more distraction)
    num_premises: int = 4

    # Maximum nesting depth of expressions
    max_depth: int = 2

    # Probability that the generated argument is valid
    # (0.5 = balanced valid/invalid)
    valid_probability: float = 0.5

    # Seed for reproducibility (None = random)
    seed: int | None = None


# Difficulty presets
EASY = GeneratorConfig(num_variables=3, num_premises=3, max_depth=1)
MEDIUM = GeneratorConfig(num_variables=4, num_premises=5, max_depth=2)
HARD = GeneratorConfig(num_variables=5, num_premises=6, max_depth=3)
EXTREME = GeneratorConfig(num_variables=6, num_premises=8, max_depth=3)


# ---------------------------------------------------------------------------
# Problem generator
# ---------------------------------------------------------------------------

class ProblemGenerator:
    """Generates fresh, unique propositional logic problems.

    Each problem gets a unique fingerprint derived from the seed and
    problem index, ensuring problems are reproducible but unique.
    """

    VARIABLE_NAMES = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    def __init__(self, config: GeneratorConfig | None = None) -> None:
        self.config = config or MEDIUM
        self.verifier = PropositionalVerifier()

        if self.config.seed is not None:
            self.rng = random.Random(self.config.seed)
        else:
            # Use current time in nanoseconds for maximum uniqueness
            self.rng = random.Random(time.time_ns())

    def generate_batch(self, count: int) -> list[dict[str, Any]]:
        """Generate a batch of fresh problems with ground truth."""
        problems = []
        for i in range(count):
            problem = self._generate_one(i)
            problems.append(problem)
        return problems

    def generate_exam(
        self, count: int, output_path: Path | None = None
    ) -> dict[str, Any]:
        """Generate a complete exam with metadata.

        Returns a dict that can be serialized to JSON. The exam includes:
        - Unique exam ID (hash-based)
        - Generation timestamp
        - Configuration used
        - Problems WITHOUT ground truth (for the LLM)
        - Answer key (separate, for verification)
        """
        # Generate unique exam ID
        seed_str = f"{self.config.seed}-{time.time_ns()}-{count}"
        exam_id = hashlib.sha256(seed_str.encode()).hexdigest()[:12]

        problems = self.generate_batch(count)

        # Split into exam (no answers) and answer key
        exam_problems = []
        answer_key = {}

        for p in problems:
            exam_problems.append({
                "id": p["id"],
                "difficulty": p["difficulty"],
                "natural_language": p["natural_language"],
                "formal": p["formal"],
            })
            answer_key[p["id"]] = {
                "valid": p["ground_truth_valid"],
                "rule": p["rule"],
                "explanation": p["explanation"],
            }

        exam = {
            "exam_id": exam_id,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "config": {
                "num_variables": self.config.num_variables,
                "num_premises": self.config.num_premises,
                "max_depth": self.config.max_depth,
                "seed": self.config.seed,
            },
            "problems": exam_problems,
            "answer_key": answer_key,
        }

        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(exam, f, indent=2, ensure_ascii=False)

        return exam

    # -----------------------------------------------------------------
    # Internal generation
    # -----------------------------------------------------------------

    def _generate_one(self, index: int) -> dict[str, Any]:
        """Generate a single problem with verified ground truth."""
        variables = [
            Proposition(name)
            for name in self.VARIABLE_NAMES[: self.config.num_variables]
        ]

        # Decide if we want a valid or invalid argument
        want_valid = self.rng.random() < self.config.valid_probability

        # Strategy: generate random premises, then either derive a
        # correct conclusion (valid) or a slightly wrong one (invalid)
        premises = self._generate_premises(variables)

        if want_valid:
            conclusion = self._derive_valid_conclusion(variables, premises)
        else:
            conclusion = self._generate_invalid_conclusion(variables, premises)

        argument = Argument(premises=premises, conclusion=conclusion)

        # Let the verifier determine ground truth
        result = self.verifier.verify(argument)

        # Build natural language
        nl = self._to_natural_language(premises, conclusion)
        formal = str(argument)

        problem_id = f"GEN-{index+1:03d}"

        return {
            "id": problem_id,
            "difficulty": self._classify_difficulty(premises, conclusion),
            "natural_language": nl,
            "formal": formal,
            "ground_truth_valid": result.valid,
            "rule": result.rule,
            "explanation": result.explanation,
            "counterexample": result.counterexample,
            "argument": argument,
        }

    def _generate_premises(
        self, variables: list[Proposition]
    ) -> list[Proposition | LogicalExpression]:
        """Generate a set of random premises."""
        premises: list[Proposition | LogicalExpression] = []

        for _ in range(self.config.num_premises):
            expr = self._random_expression(variables, depth=0)
            premises.append(expr)

        return premises

    def _random_expression(
        self, variables: list[Proposition], depth: int
    ) -> Proposition | LogicalExpression:
        """Generate a random logical expression up to max_depth."""
        # At max depth or with some probability, return an atom
        if depth >= self.config.max_depth or self.rng.random() < 0.4:
            return self.rng.choice(variables)

        connective = self.rng.choice(list(Connective))

        if connective is Connective.NOT:
            operand = self._random_expression(variables, depth + 1)
            return LogicalExpression(Connective.NOT, operand)

        left = self._random_expression(variables, depth + 1)
        right = self._random_expression(variables, depth + 1)
        return LogicalExpression(connective, left, right)

    def _derive_valid_conclusion(
        self,
        variables: list[Proposition],
        premises: list[Proposition | LogicalExpression],
    ) -> Proposition | LogicalExpression:
        """Try to find a conclusion that validly follows from premises.

        Strategy: Try random conclusions and check with Z3.
        If none found after N tries, fall back to a premise (trivially valid).
        """
        for _ in range(20):
            candidate = self._random_expression(variables, depth=0)
            arg = Argument(premises=premises, conclusion=candidate)
            result = self.verifier.verify(arg)
            if result.valid:
                return candidate

        # Fallback: use a premise as conclusion (trivially valid)
        return self.rng.choice(premises)

    def _generate_invalid_conclusion(
        self,
        variables: list[Proposition],
        premises: list[Proposition | LogicalExpression],
    ) -> Proposition | LogicalExpression:
        """Generate a conclusion that does NOT follow from premises.

        Strategy: Try random conclusions and check with Z3.
        If none found, negate a premise (usually invalid).
        """
        for _ in range(20):
            candidate = self._random_expression(variables, depth=0)
            arg = Argument(premises=premises, conclusion=candidate)
            result = self.verifier.verify(arg)
            if not result.valid:
                return candidate

        # Fallback: negate a random premise
        premise = self.rng.choice(premises)
        return LogicalExpression(Connective.NOT, premise)

    # -----------------------------------------------------------------
    # Natural language rendering
    # -----------------------------------------------------------------

    def _to_natural_language(
        self,
        premises: list[Proposition | LogicalExpression],
        conclusion: Proposition | LogicalExpression,
    ) -> str:
        """Render a problem as natural language."""
        parts = ["Given the following premises:"]
        for i, p in enumerate(premises, 1):
            parts.append(f"  {i}. {self._expr_to_nl(p)}")
        parts.append(f"Conclusion: {self._expr_to_nl(conclusion)}")
        parts.append("Is this conclusion logically valid?")
        return "\n".join(parts)

    def _expr_to_nl(self, expr: Proposition | LogicalExpression) -> str:
        """Convert an expression to readable natural language."""
        if isinstance(expr, Proposition):
            return f"{expr.label} is true"

        if expr.connective is Connective.NOT:
            inner = self._expr_to_nl(expr.left)
            # Clean up double "is true"
            if inner.endswith(" is true"):
                return inner[:-8] + " is false"
            return f"it is not the case that ({inner})"

        left = self._expr_to_nl(expr.left)
        right = self._expr_to_nl(expr.right) if expr.right else ""

        if expr.connective is Connective.AND:
            return f"({left}) and ({right})"
        elif expr.connective is Connective.OR:
            return f"({left}) or ({right})"
        elif expr.connective is Connective.IMPLIES:
            return f"if ({left}) then ({right})"
        elif expr.connective is Connective.IFF:
            return f"({left}) if and only if ({right})"

        return str(expr)

    # -----------------------------------------------------------------
    # Difficulty classification
    # -----------------------------------------------------------------

    def _classify_difficulty(
        self,
        premises: list[Proposition | LogicalExpression],
        conclusion: Proposition | LogicalExpression,
    ) -> str:
        """Heuristic difficulty classification."""
        total_depth = sum(self._expr_depth(p) for p in premises)
        total_depth += self._expr_depth(conclusion)
        num_atoms = len(self._collect_all_atoms(premises, conclusion))

        if total_depth <= 4 and num_atoms <= 3:
            return "easy"
        elif total_depth <= 8 and num_atoms <= 4:
            return "medium"
        elif total_depth <= 14:
            return "hard"
        else:
            return "extreme"

    def _expr_depth(self, expr: Proposition | LogicalExpression) -> int:
        if isinstance(expr, Proposition):
            return 0
        d = self._expr_depth(expr.left)
        if expr.right:
            d = max(d, self._expr_depth(expr.right))
        return d + 1

    def _collect_all_atoms(
        self,
        premises: list[Proposition | LogicalExpression],
        conclusion: Proposition | LogicalExpression,
    ) -> set[str]:
        atoms: set[str] = set()
        for p in premises:
            self._collect_from(p, atoms)
        self._collect_from(conclusion, atoms)
        return atoms

    def _collect_from(
        self, expr: Proposition | LogicalExpression, atoms: set[str]
    ) -> None:
        if isinstance(expr, Proposition):
            atoms.add(expr.label)
        elif isinstance(expr, LogicalExpression):
            self._collect_from(expr.left, atoms)
            if expr.right:
                self._collect_from(expr.right, atoms)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    difficulty = sys.argv[1] if len(sys.argv) > 1 else "medium"
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    configs = {"easy": EASY, "medium": MEDIUM, "hard": HARD, "extreme": EXTREME}
    config = configs.get(difficulty, MEDIUM)

    gen = ProblemGenerator(config)
    exam = gen.generate_exam(count)

    # Print exam (without answer key)
    print(f"# Logic Exam [{exam['exam_id']}]\n")
    print(f"Difficulty: {difficulty} | Problems: {count}\n")
    print(f"Generated: {exam['generated_at']}\n")
    print("=" * 60)

    for p in exam["problems"]:
        print(f"\n## {p['id']} [{p['difficulty']}]\n")
        print(p["natural_language"])
        print(f"\nFormal: {p['formal']}")
        print("-" * 40)

    # Print answer key separately
    print("\n\n" + "=" * 60)
    print("# ANSWER KEY (do not show to LLM)\n")
    for pid, answer in exam["answer_key"].items():
        v = "VALID" if answer["valid"] else "INVALID"
        print(f"{pid}: {v} [{answer['rule']}]")
