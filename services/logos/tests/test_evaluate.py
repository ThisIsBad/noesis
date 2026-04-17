"""Direct tests for logos.evaluate."""

from __future__ import annotations

import json

from logos.evaluate import evaluate


def _make_problem(expected_valid: bool) -> dict[str, object]:
    return {
        "id": "L1-01",
        "level": 1,
        "category": "sanity",
        "premises": ["P"],
        "conclusion": "P",
        "expected_valid": expected_valid,
        "natural_language": "If P then P.",
        "explanation": "Simple sanity check.",
    }


def test_evaluate_reports_perfect_accuracy(monkeypatch, tmp_path):
    monkeypatch.setattr("logos.evaluate.load_problems", lambda: [_make_problem(True)])

    answers_path = tmp_path / "answers.json"
    answers_path.write_text(
        json.dumps({"answers": {"L1-01": {"valid": True, "reasoning": "tautological"}}}),
        encoding="utf-8",
    )

    report = evaluate(answers_path)

    assert "Accuracy: 100%" in report
    assert "LLM reasoning" in report
    assert "L1-01" in report


def test_evaluate_includes_error_analysis_when_wrong(monkeypatch, tmp_path):
    monkeypatch.setattr("logos.evaluate.load_problems", lambda: [_make_problem(True)])

    answers_path = tmp_path / "answers.json"
    answers_path.write_text(
        json.dumps({"answers": {"L1-01": {"valid": False}}}),
        encoding="utf-8",
    )

    report = evaluate(answers_path)

    assert "Accuracy: 0%" in report
    assert "LLM got this **wrong**!" in report
    assert "Error Analysis" in report
