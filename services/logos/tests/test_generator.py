"""Tests for logos.generator — problem generation with verified ground truth."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


from logos.generator import (
    EASY,
    EXTREME,
    HARD,
    MEDIUM,
    GeneratorConfig,
    ProblemGenerator,
)
from logos.models import Argument


class TestGeneratorConfig:
    """Verify preset configurations are sane."""

    def test_presets_exist(self):
        for preset in (EASY, MEDIUM, HARD, EXTREME):
            assert isinstance(preset, GeneratorConfig)
            assert preset.num_variables >= 1
            assert preset.num_premises >= 1
            assert preset.max_depth >= 1

    def test_presets_increase_difficulty(self):
        assert EASY.num_variables <= MEDIUM.num_variables <= HARD.num_variables
        assert EASY.num_premises <= MEDIUM.num_premises <= HARD.num_premises


class TestProblemGenerator:
    """Core generation tests."""

    def test_generate_batch_returns_correct_count(self):
        gen = ProblemGenerator(GeneratorConfig(seed=42, num_variables=3, num_premises=3, max_depth=1))
        batch = gen.generate_batch(5)
        assert len(batch) == 5

    def test_generated_problems_have_required_keys(self):
        gen = ProblemGenerator(GeneratorConfig(seed=42))
        batch = gen.generate_batch(3)
        required = {
            "id",
            "difficulty",
            "natural_language",
            "formal",
            "ground_truth_valid",
            "rule",
            "explanation",
            "argument",
        }
        for problem in batch:
            assert required.issubset(problem.keys()), f"Missing keys in {problem['id']}"

    def test_ground_truth_is_bool(self):
        gen = ProblemGenerator(GeneratorConfig(seed=42))
        batch = gen.generate_batch(5)
        for p in batch:
            assert isinstance(p["ground_truth_valid"], bool)

    def test_argument_is_model_object(self):
        gen = ProblemGenerator(GeneratorConfig(seed=42))
        batch = gen.generate_batch(2)
        for p in batch:
            assert isinstance(p["argument"], Argument)

    def test_seed_determinism(self):
        """Same seed must produce identical problems."""
        cfg = GeneratorConfig(seed=999, num_variables=3, num_premises=3, max_depth=1)
        batch_a = ProblemGenerator(cfg).generate_batch(5)
        batch_b = ProblemGenerator(cfg).generate_batch(5)
        for a, b in zip(batch_a, batch_b):
            assert a["formal"] == b["formal"]
            assert a["ground_truth_valid"] == b["ground_truth_valid"]

    def test_different_seeds_differ(self):
        """Different seeds should (almost certainly) produce different problems."""
        batch_a = ProblemGenerator(GeneratorConfig(seed=1)).generate_batch(5)
        batch_b = ProblemGenerator(GeneratorConfig(seed=2)).generate_batch(5)
        formals_a = [p["formal"] for p in batch_a]
        formals_b = [p["formal"] for p in batch_b]
        assert formals_a != formals_b


class TestGenerateExam:
    """Test the exam generation wrapper."""

    def test_exam_structure(self):
        gen = ProblemGenerator(GeneratorConfig(seed=42, num_variables=3, num_premises=3, max_depth=1))
        exam = gen.generate_exam(3)
        assert "exam_id" in exam
        assert "generated_at" in exam
        assert "config" in exam
        assert "problems" in exam
        assert "answer_key" in exam
        assert len(exam["problems"]) == 3
        assert len(exam["answer_key"]) == 3

    def test_exam_problems_have_no_answers(self):
        """Exam problems must not leak ground truth to the LLM."""
        gen = ProblemGenerator(GeneratorConfig(seed=42))
        exam = gen.generate_exam(3)
        for p in exam["problems"]:
            assert "ground_truth_valid" not in p
            assert "rule" not in p

    def test_exam_write_to_file(self):
        gen = ProblemGenerator(GeneratorConfig(seed=42, num_variables=3, num_premises=3, max_depth=1))
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            path = Path(f.name)
        try:
            exam = gen.generate_exam(2, output_path=path)
            loaded = json.loads(path.read_text(encoding="utf-8"))
            assert loaded["exam_id"] == exam["exam_id"]
            assert len(loaded["problems"]) == 2
        finally:
            path.unlink(missing_ok=True)


class TestDifficultyClassification:
    """Verify that the heuristic difficulty label is always present and valid."""

    def test_difficulty_label_is_valid(self):
        gen = ProblemGenerator(GeneratorConfig(seed=42))
        batch = gen.generate_batch(10)
        valid_labels = {"easy", "medium", "hard", "extreme"}
        for p in batch:
            assert p["difficulty"] in valid_labels, f"{p['id']} has unknown difficulty {p['difficulty']}"
