"""Tests for the module CLI (`python -m logos`)."""

from __future__ import annotations

import json
import subprocess
import sys


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "logos", *args],
        capture_output=True,
        text=True,
    )


def test_cli_plain_output_valid_argument():
    process = _run_cli("P -> Q, P |- Q")

    assert process.returncode == 0
    assert "valid=True" in process.stdout
    assert "rule=Modus Ponens" in process.stdout


def test_cli_json_output_valid_argument():
    process = _run_cli("P -> Q, P |- Q", "--json")

    assert process.returncode == 0
    payload = json.loads(process.stdout)
    assert payload["valid"] is True
    assert payload["rule"] == "Modus Ponens"
    assert "explanation" not in payload


def test_cli_json_with_explain_includes_details():
    process = _run_cli("P -> Q, Q |- P", "--json", "--explain")

    assert process.returncode == 0
    payload = json.loads(process.stdout)
    assert payload["valid"] is False
    assert "fallacy" in payload["rule"].lower()
    assert isinstance(payload["explanation"], str)
    assert isinstance(payload["counterexample"], dict)


def test_cli_parse_error_json_returns_nonzero_with_error_payload():
    process = _run_cli("P @ Q |- Q", "--json")

    assert process.returncode == 2
    payload = json.loads(process.stdout)
    assert payload["error"] == "parse_error"
    assert "Unexpected character" in payload["message"]
