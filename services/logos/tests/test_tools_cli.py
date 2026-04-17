"""Smoke tests for tools/* command-line entrypoints."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_generate_exam_tool_runs(tmp_path: Path):
    output = tmp_path / "exam.json"
    process = _run_tool(
        "tools/generate_exam.py",
        "--count",
        "1",
        "--vars",
        "3",
        "--premises",
        "2",
        "--depth",
        "1",
        "--seed",
        "7",
        "--output",
        str(output),
    )

    assert process.returncode == 0, process.stderr
    assert output.exists()

    data = json.loads(output.read_text(encoding="utf-8"))
    assert "answer_key" in data
    assert len(data["problems"]) == 1


def test_generate_hardmode_tool_runs(tmp_path: Path):
    output = tmp_path / "hardmode.json"
    process = _run_tool(
        "tools/generate_hardmode.py",
        "--vars",
        "4",
        "--premises",
        "4",
        "--count",
        "1",
        "--depth",
        "2",
        "--seed",
        "9",
        "--output",
        str(output),
    )

    assert process.returncode == 0, process.stderr
    assert output.exists()


def test_generate_escalation_tool_runs(tmp_path: Path):
    output = tmp_path / "escalation.json"
    process = _run_tool(
        "tools/generate_escalation.py",
        "round1",
        "--count",
        "1",
        "--seed",
        "11",
        "--output",
        str(output),
    )

    assert process.returncode == 0, process.stderr
    assert output.exists()


def test_check_stress_results_tool_happy_path(tmp_path: Path):
    bench = tmp_path / "stress.json"
    answers = tmp_path / "stress_answers.json"

    bench.write_text(
        json.dumps(
            {
                "problems": [
                    {"id": "L4-TEST-01", "expected_valid": True},
                ]
            }
        ),
        encoding="utf-8",
    )
    answers.write_text(
        json.dumps(
            {
                "answers": {
                    "L4-TEST-01": {"valid": True, "reasoning": "dummy"},
                }
            }
        ),
        encoding="utf-8",
    )

    process = _run_tool(
        "tools/check_stress_results.py",
        "--benchmarks",
        str(bench),
        "--answers",
        str(answers),
    )

    assert process.returncode == 0, process.stdout + process.stderr
    assert "Score: 1/1" in process.stdout


def test_check_fol_results_tool_happy_path(tmp_path: Path):
    bench = tmp_path / "fol.json"
    answers = tmp_path / "fol_answers.json"

    bench.write_text(
        json.dumps(
            {
                "problems": [
                    {"id": "FOL-T-01", "expected_valid": False},
                ]
            }
        ),
        encoding="utf-8",
    )
    answers.write_text(
        json.dumps(
            {
                "answers": {
                    "FOL-T-01": {"valid": False, "reasoning": "dummy"},
                }
            }
        ),
        encoding="utf-8",
    )

    process = _run_tool(
        "tools/check_fol_results.py",
        "--benchmarks",
        str(bench),
        "--answers",
        str(answers),
    )

    assert process.returncode == 0, process.stdout + process.stderr
    assert "Score: 1/1" in process.stdout


def test_issue_autopilot_dry_run_with_overrides(tmp_path: Path):
    known_titles = tmp_path / "known_titles.json"
    known_titles.write_text("[]", encoding="utf-8")

    process = _run_tool(
        "tools/issue_autopilot.py",
        "--open-count-override",
        "0",
        "--known-titles-file",
        str(known_titles),
    )

    assert process.returncode == 0, process.stdout + process.stderr
    assert "Dry-run mode" in process.stdout
