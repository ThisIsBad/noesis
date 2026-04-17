"""Tests for the check_beliefs MCP handler."""

from __future__ import annotations

from typing import cast

import pytest

from logos.mcp_tools import check_beliefs


def test_check_beliefs_returns_consistent_for_compatible_beliefs() -> None:
    result = check_beliefs(
        {
            "beliefs": [
                {"id": "b1", "statement": "x > 0"},
                {"id": "b2", "statement": "x < 10"},
            ],
            "variables": {"x": "Int"},
        }
    )

    assert result["status"] == "consistent"
    assert result["contradiction_count"] == 0


def test_check_beliefs_detects_contradictions() -> None:
    result = check_beliefs(
        {
            "beliefs": [
                {"id": "b1", "statement": "x > 0"},
                {"id": "b2", "statement": "x < -5"},
            ],
            "variables": {"x": "Int"},
        }
    )

    assert result["status"] == "contradictions_found"
    assert result["contradiction_count"] == 1


def test_check_beliefs_handles_empty_belief_list() -> None:
    result = check_beliefs({"beliefs": []})

    assert result["status"] == "consistent"
    assert result["belief_count"] == 0


def test_check_beliefs_auto_declares_variables_when_omitted() -> None:
    result = check_beliefs(
        {
            "beliefs": [
                {"id": "b1", "statement": "x > 0"},
                {"id": "b2", "statement": "x < 10"},
            ]
        }
    )

    assert result["status"] == "consistent"


def test_check_beliefs_returns_explanations_with_correct_ids() -> None:
    result = check_beliefs(
        {
            "beliefs": [
                {"id": "b1", "statement": "x > 0"},
                {"id": "b2", "statement": "x < 0"},
            ],
            "variables": {"x": "Int"},
        }
    )

    explanation = cast(list[dict[str, object]], result["explanations"])[0]
    assert explanation["left_id"] == "b1"
    assert explanation["right_id"] == "b2"
    assert explanation["witness_ids"] == ["b1", "b2"]


def test_check_beliefs_surfaces_unknown_status(monkeypatch: pytest.MonkeyPatch) -> None:
    from logos.z3_session import CheckResult

    def fake_check(self: object) -> CheckResult:
        return CheckResult(status="unknown", satisfiable=None, reason="timeout")

    monkeypatch.setattr("logos.z3_session.Z3Session.check", fake_check)

    result = check_beliefs(
        {
            "beliefs": [
                {"id": "b1", "statement": "x * x == 2"},
                {"id": "b2", "statement": "x * x == 3"},
            ],
            "variables": {"x": "Int"},
        }
    )

    assert result["status"] == "unknown"
    assert result["reason"] == "timeout"
