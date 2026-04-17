"""Direct tests for logos.loader."""

from __future__ import annotations

import json

from logos.loader import load_problems, parse_problem
from logos.models import Proposition


def test_load_problems_reads_json_file(tmp_path):
    payload = {
        "problems": [
            {
                "id": "L1-01",
                "level": 1,
                "category": "sanity",
                "premises": ["P"],
                "conclusion": "P",
                "expected_valid": True,
            }
        ]
    }
    path = tmp_path / "problems.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    problems = load_problems(path)
    assert len(problems) == 1
    assert problems[0]["id"] == "L1-01"


def test_parse_problem_returns_argument_and_metadata():
    raw = {
        "id": "L1-01",
        "level": 1,
        "category": "sanity",
        "premises": ["P"],
        "conclusion": "P",
        "expected_valid": True,
        "explanation": "Simple identity",
        "natural_language": "P therefore P",
    }

    argument, meta = parse_problem(raw)
    assert isinstance(argument.premises[0], Proposition)
    assert argument.natural_language == "P therefore P"
    assert meta["id"] == "L1-01"
    assert meta["expected_valid"] is True
