from __future__ import annotations

import pytest

from examples import reflective_agent


def test_reflective_agent_demo_returns_expected_reflective_flow() -> None:
    summary = reflective_agent.run_reflective_demo()

    assert summary["verify_argument"]["valid"] is True
    assert summary["failed_assumption_check"]["consistent"] is False
    assert summary["repaired_assumption_check"]["consistent"] is True
    assert summary["blocked_contract"]["status"] == "blocked"
    assert summary["active_contract"]["status"] == "active"
    assert summary["proof_carrying_action"]["status"] == "completed"
    assert summary["proof_carrying_action"]["accepted"] is True


def test_reflective_agent_main_prints_stage3_trace(capsys: pytest.CaptureFixture[str]) -> None:
    reflective_agent.main()

    output = capsys.readouterr().out

    for step in (
        "-- Step 1: verify_argument --",
        "-- Step 2: check_assumptions --",
        "-- Step 3: check_contract --",
        "-- Step 4: proof_carrying_action --",
        "-- MCP stdio parity --",
    ):
        assert step in output

    assert "first_pass_consistent=False" in output
    assert "replanned_status=active" in output
    assert "action_status=completed" in output
    assert "python -m logos.mcp_server" in output


def test_reflective_agent_stdio_requests_cover_required_tools() -> None:
    requests = reflective_agent.build_stdio_requests()

    assert [request["tool"] for request in requests] == [
        "verify_argument",
        "check_assumptions",
        "check_contract",
        "proof_carrying_action",
    ]
