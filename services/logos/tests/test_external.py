"""Tests for logos.external — external benchmark loaders."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from logos.external import load_folio, load_satbench


def _write_jsonl(lines: list[dict], suffix: str = ".jsonl") -> Path:
    """Helper: write a list of dicts as a JSONL temp file."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8")
    for obj in lines:
        tmp.write(json.dumps(obj) + "\n")
    tmp.close()
    return Path(tmp.name)


class TestLoadSATBench:

    def test_basic_loading(self):
        data = [
            {"scenario": "A puzzle", "conditions": ["x > 0"], "question": "Is x positive?", "label": "SAT"},
            {"scenario": "Another", "conditions": [], "question": "?", "label": "UNSAT"},
        ]
        path = _write_jsonl(data)
        try:
            problems = load_satbench(path)
            assert len(problems) == 2
            assert problems[0]["id"] == "SAT-0001"
            assert problems[0]["source"] == "SATBench"
            assert problems[0]["expected_satisfiable"] is True
            assert problems[1]["expected_satisfiable"] is False
        finally:
            path.unlink(missing_ok=True)

    def test_natural_language_format(self):
        data = [{"scenario": "Ctx", "conditions": ["c1", "c2"], "question": "Q?", "label": "SAT"}]
        path = _write_jsonl(data)
        try:
            problems = load_satbench(path)
            nl = problems[0]["natural_language"]
            assert "Ctx" in nl
            assert "c1" in nl
            assert "Q?" in nl
        finally:
            path.unlink(missing_ok=True)

    def test_missing_label_defaults_to_unsat(self):
        data = [{"scenario": "No label"}]
        path = _write_jsonl(data)
        try:
            problems = load_satbench(path)
            assert problems[0]["expected_satisfiable"] is False
        finally:
            path.unlink(missing_ok=True)


class TestLoadFOLIO:

    def test_basic_loading(self):
        data = [
            {"premises": ["All men are mortal"], "conclusion": "Socrates is mortal", "label": "True"},
            {"premises": ["Some cats fly"], "conclusion": "All cats fly", "label": "False"},
        ]
        path = _write_jsonl(data)
        try:
            problems = load_folio(path)
            assert len(problems) == 2
            assert problems[0]["id"] == "FOLIO-0001"
            assert problems[0]["source"] == "FOLIO"
            assert problems[0]["expected_label"] == "True"
            assert problems[1]["expected_label"] == "False"
        finally:
            path.unlink(missing_ok=True)

    def test_unknown_label(self):
        data = [{"premises": ["P"], "conclusion": "Q"}]
        path = _write_jsonl(data)
        try:
            problems = load_folio(path)
            assert problems[0]["expected_label"] == "Unknown"
        finally:
            path.unlink(missing_ok=True)

    def test_natural_language_format(self):
        data = [{"premises": ["A", "B"], "conclusion": "C", "label": "True"}]
        path = _write_jsonl(data)
        try:
            problems = load_folio(path)
            nl = problems[0]["natural_language"]
            assert "Premises:" in nl
            assert "A" in nl
            assert "Conclusion: C" in nl
        finally:
            path.unlink(missing_ok=True)
