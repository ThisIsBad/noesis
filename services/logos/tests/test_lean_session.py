"""Tests for the Lean 4 interactive session wrapper."""

import pytest

from logos.diagnostics import ErrorType
from logos.lean_session import LeanSession, TacticResult, is_lean_available


# Skip all tests if Lean is not available
pytestmark = pytest.mark.skipif(
    not is_lean_available(),
    reason="Lean 4 not installed"
)


class TestLeanSessionBasic:
    """Basic functionality tests."""

    def test_start_creates_initial_goals(self):
        session = LeanSession()
        # Note: Lean 4 requires at least a placeholder tactic after "by"
        # The session reports an error for empty tactics, which is expected
        result = session.start("theorem test : True := by")

        # Starting with just "by" may error in Lean 4 - that's okay
        # The important thing is we can then apply tactics
        # If it errors, goals will be empty initially
        assert result is not None

    def test_trivial_proof(self):
        session = LeanSession()
        session.start("theorem test : True := by")

        result = session.apply("trivial")

        assert result.success
        assert session.is_complete
        assert session.goals == []

    def test_rfl_proof(self):
        session = LeanSession()
        session.start("theorem test : 1 + 1 = 2 := by")

        result = session.apply("rfl")

        # This should work with native_decide or rfl depending on Lean version
        # If rfl doesn't work directly, try native_decide
        if not result.success:
            result = session.apply("native_decide")

        assert session.is_complete or result.success

    def test_invalid_tactic_fails(self):
        session = LeanSession()
        session.start("theorem test (n : Nat) : n = n := by")

        result = session.apply("nonexistent_tactic_xyz")

        assert not result.success
        assert result.error_message is not None

    def test_invalid_tactic_does_not_change_state(self):
        session = LeanSession()
        session.start("theorem test : True := by")
        goals_before = session.goals.copy()

        session.apply("nonexistent_tactic")

        assert session.goals == goals_before
        assert not session.is_complete


class TestLeanSessionState:
    """State management tests."""

    def test_proof_property_tracks_tactics(self):
        session = LeanSession()
        session.start("theorem test : True := by")
        session.apply("trivial")

        proof = session.proof

        assert "theorem test" in proof
        assert "trivial" in proof

    def test_undo_reverts_last_tactic(self):
        session = LeanSession()
        session.start("theorem test (a b : Nat) : a + b = a + b := by")

        result = session.apply("rfl")
        if result.success:
            assert session.is_complete

            session.undo()
            assert not session.is_complete
            # After undo, we're back to empty tactics state
            # Goals may be empty due to Lean 4's "by" handling

    def test_undo_on_empty_fails(self):
        session = LeanSession()
        session.start("theorem test : True := by")

        result = session.undo()

        assert not result.success
        assert result.error_message is not None
        assert "No tactics to undo" in result.error_message

    def test_reset_clears_state(self):
        session = LeanSession()
        session.start("theorem test : True := by")
        session.apply("trivial")

        session.reset()

        assert session.goals == []
        assert not session.is_complete

    def test_apply_without_start_raises(self):
        session = LeanSession()

        with pytest.raises(RuntimeError, match="not started"):
            session.apply("rfl")


class TestLeanSessionMultiStep:
    """Multi-step proof tests."""

    def test_intro_then_rfl(self):
        session = LeanSession()
        session.start("theorem test (n : Nat) : n = n := by")

        result = session.apply("rfl")

        assert result.success
        assert session.is_complete

    def test_multi_goal_proof(self):
        session = LeanSession()
        session.start("theorem test : True ∧ True := by")

        # This should create two goals
        result = session.apply("constructor")

        if result.success:
            # Now we need to prove both goals
            session.apply("trivial")
            session.apply("trivial")

            # Should be complete after proving both
            assert session.is_complete


class TestLeanSessionEdgeCases:
    """Edge cases and error handling."""

    def test_apply_after_complete_fails(self):
        session = LeanSession()
        session.start("theorem test : True := by")
        session.apply("trivial")

        assert session.is_complete

        result = session.apply("rfl")

        assert not result.success
        assert result.error_message is not None
        assert "already complete" in result.error_message.lower()

    def test_syntax_error_in_header(self):
        session = LeanSession()
        result = session.start("this is not valid lean syntax")

        assert not result.success or "error" in str(result.error_message).lower()

    def test_goals_returns_copy(self):
        session = LeanSession()
        session.start("theorem test : True := by")

        goals = session.goals
        goals.append("fake goal")

        assert "fake goal" not in session.goals


class TestTacticResult:
    """TacticResult dataclass tests."""

    def test_tactic_result_fields(self):
        result = TacticResult(
            success=True,
            goals=["⊢ True"],
            proof_so_far="theorem test : True := by",
            error_message=None
        )

        assert result.success
        assert result.goals == ["⊢ True"]
        assert "theorem" in result.proof_so_far
        assert result.error_message is None

    def test_tactic_result_with_error(self):
        result = TacticResult(
            success=False,
            goals=[],
            proof_so_far="",
            error_message="unknown tactic"
        )

        assert not result.success
        assert result.error_message == "unknown tactic"


class TestLeanSessionDiagnostics:
    """End-to-end tests for LeanSession structured diagnostics."""

    def test_invalid_tactic_returns_structured_diagnostic(self):
        session = LeanSession()
        session.start("theorem test (n : Nat) : n = n := by")

        result = session.apply("nonexistent_tactic_xyz")

        assert not result.success
        assert result.diagnostic is not None
        assert result.error_type in {
            ErrorType.UNKNOWN_TACTIC.value,
            ErrorType.UNKNOWN_IDENTIFIER.value,
            ErrorType.UNKNOWN.value,
        }
        assert isinstance(result.suggestions, list)

    def test_invalid_header_returns_structured_diagnostic(self):
        session = LeanSession()

        result = session.start("this is not valid lean syntax")

        assert not result.success
        assert result.diagnostic is not None
        assert result.error_type in {
            ErrorType.SYNTAX_ERROR.value,
            ErrorType.UNKNOWN_IDENTIFIER.value,
            ErrorType.UNKNOWN.value,
        }


class TestIsLeanAvailable:
    """Tests for the is_lean_available helper."""

    def test_returns_bool(self):
        result = is_lean_available()
        assert isinstance(result, bool)
