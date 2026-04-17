"""Tests for the check_contract MCP handler."""

from __future__ import annotations

from typing import cast

from logos.mcp_tools import check_contract


def test_check_contract_returns_active_for_entailed_preconditions() -> None:
    result = check_contract(
        {
            "contract": {"contract_id": "c1", "preconditions": ["x > 0"]},
            "state_constraints": ["x == 5"],
            "variables": {"x": "Int"},
        }
    )

    assert result["status"] == "active"
    assert result["solver_status"] == "unsat"


def test_check_contract_returns_blocked_for_unentailed_precondition() -> None:
    result = check_contract(
        {
            "contract": {"contract_id": "c1", "preconditions": ["x > 0"]},
            "state_constraints": ["x == -1"],
            "variables": {"x": "Int"},
        }
    )

    assert result["status"] == "blocked"
    assert result["solver_status"] == "unsat"


def test_check_contract_handles_empty_preconditions() -> None:
    result = check_contract(
        {
            "contract": {"contract_id": "c1", "preconditions": []},
            "state_constraints": ["x == -1"],
            "variables": {"x": "Int"},
        }
    )

    assert result["status"] == "active"


def test_check_contract_rejects_missing_contract_id() -> None:
    result = check_contract(
        {
            "contract": {"preconditions": ["x > 0"]},
            "state_constraints": ["x == 5"],
            "variables": {"x": "Int"},
        }
    )

    assert result["error"] == "Invalid input"


def test_check_contract_returns_diagnostics_with_code_and_message() -> None:
    result = check_contract(
        {
            "contract": {"contract_id": "c1", "preconditions": ["x > 0"]},
            "state_constraints": ["x == -1"],
            "variables": {"x": "Int"},
        }
    )

    diagnostic = cast(list[dict[str, object]], result["diagnostics"])[0]
    assert set(diagnostic) == {"code", "message"}


def test_check_contract_returns_unsat_core_for_inconsistent_preconditions() -> None:
    result = check_contract(
        {
            "contract": {"contract_id": "c1", "preconditions": ["x > 0", "x < 0"]},
            "state_constraints": ["x == 1"],
            "variables": {"x": "Int"},
        }
    )

    assert result["status"] == "blocked"
    assert result["unsat_core"] == ["x > 0", "x < 0"]
