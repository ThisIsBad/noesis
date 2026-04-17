from __future__ import annotations

import pytest

from examples import full_reasoning_loop


def test_full_reasoning_loop_example_runs_in_pytest(capsys: pytest.CaptureFixture[str]) -> None:
    full_reasoning_loop.main()

    captured = capsys.readouterr()
    output = captured.out

    for step in (
        "-- Step 1: Assumptions --",
        "-- Step 2: Belief Graph --",
        "-- Step 3: Counterfactual Planning --",
        "-- Step 4: Goal Contract --",
        "-- Step 5: Uncertainty Calibration --",
        "-- Step 6: End-to-End Certificate --",
    ):
        assert step in output

    assert "Assumptions consistent (Z3): True" in output
    assert "After adding x > 200:  consistent (Z3): False" in output
    assert "After retraction:      consistent (Z3): True" in output
    assert "Z3-detected contradictions: ((\'b1\', \'b3\'),)" in output

    assert "conservative: sat (sat=True)" in output
    assert "aggressive:   sat (sat=True)" in output
    assert "impossible:   unsat (sat=False)" in output
    assert "All branch certificates independently verified." in output

    assert "Z3 precondition check (x=42): active" in output
    assert "Z3 precondition check (x=150): blocked" in output
    assert "Boolean context check: blocked" in output

    assert "Verified claim confidence: certain" in output
    assert "Invalid claim confidence:  weak" in output
    assert "Final certificate verified: True" in output

    assert "[Z3] Assumption consistency:    PROVEN" in output
    assert "[Z3] Belief contradictions:     DETECTED" in output
    assert "[Z3] Goal preconditions:        PROVEN" in output
    assert "[BOOL] Boolean context matching" in output
    assert "[HEUR] Uncertainty classification" in output
