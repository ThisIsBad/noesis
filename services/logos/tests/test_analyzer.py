"""Tests for logos.analyzer — error pattern analysis."""

from __future__ import annotations

from logos.analyzer import AnalysisReport, ErrorAnalyzer


def _make_result(expected: bool, said: bool, category: str = "misc", level: str = "1") -> dict:
    return {
        "problem_id": "T-001",
        "level": level,
        "category": category,
        "expected_valid": expected,
        "llm_said_valid": said,
    }


class TestErrorAnalyzer:

    def test_perfect_score(self):
        results = [
            _make_result(True, True),
            _make_result(False, False),
        ]
        report = ErrorAnalyzer().analyze(results)
        assert report.total_problems == 2
        assert report.correct == 2
        assert report.incorrect == 0
        assert report.accuracy == 1.0
        assert report.false_positives == 0
        assert report.false_negatives == 0

    def test_all_wrong(self):
        results = [
            _make_result(True, False),
            _make_result(False, True),
        ]
        report = ErrorAnalyzer().analyze(results)
        assert report.correct == 0
        assert report.incorrect == 2
        assert report.accuracy == 0.0
        assert report.false_positives == 1
        assert report.false_negatives == 1

    def test_empty_input(self):
        report = ErrorAnalyzer().analyze([])
        assert report.total_problems == 0
        assert report.accuracy == 0.0

    def test_errors_by_category_and_level(self):
        results = [
            _make_result(True, False, category="modus_ponens", level="2"),
            _make_result(True, False, category="modus_ponens", level="2"),
            _make_result(False, True, category="affirming_consequent", level="3"),
        ]
        report = ErrorAnalyzer().analyze(results)
        assert report.errors_by_category["modus_ponens"] == 2
        assert report.errors_by_category["affirming_consequent"] == 1
        assert report.errors_by_level["2"] == 2
        assert report.errors_by_level["3"] == 1

    def test_most_common_errors_sorted(self):
        results = [
            _make_result(True, False, category="A"),
            _make_result(True, False, category="B"),
            _make_result(True, False, category="B"),
        ]
        report = ErrorAnalyzer().analyze(results)
        assert report.most_common_errors[0] == ("B", 2)


class TestAnalysisReport:

    def test_to_markdown_contains_accuracy(self):
        report = AnalysisReport(
            total_problems=10,
            correct=7,
            incorrect=3,
            accuracy=0.7,
            errors_by_category={"mp": 2, "mt": 1},
            errors_by_level={"1": 1, "2": 2},
            most_common_errors=[("mp", 2), ("mt", 1)],
            false_positives=2,
            false_negatives=1,
        )
        md = report.to_markdown()
        assert "70.0%" in md
        assert "7/10" in md
        assert "False positives" in md

    def test_to_markdown_empty_sections(self):
        report = AnalysisReport(
            total_problems=0,
            correct=0,
            incorrect=0,
            accuracy=0.0,
            errors_by_category={},
            errors_by_level={},
            most_common_errors=[],
            false_positives=0,
            false_negatives=0,
        )
        md = report.to_markdown()
        assert "Accuracy" in md
        # Should not crash on empty dicts
        assert "Errors by Difficulty" not in md
