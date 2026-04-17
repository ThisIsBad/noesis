"""Tests for logos.lean_verifier — non-interactive Lean 4 verification.

All tests that require the Lean compiler are skipped when Lean is not installed.
"""

from __future__ import annotations

import pytest

from logos.lean_verifier import LeanVerificationResult, LeanVerifier
from logos.lean_session import LeanSession, is_lean_available


def _lean_path() -> str:
    """Return the Lean executable path found by LeanSession, or 'lean' as fallback."""
    try:
        return LeanSession._find_lean()
    except FileNotFoundError:
        return "lean"


class TestLeanVerificationResult:
    """Test the result dataclass (no Lean required)."""

    def test_valid_result(self):
        r = LeanVerificationResult(valid=True, output="ok")
        assert r.valid is True
        assert r.error is None

    def test_invalid_result_with_error(self):
        r = LeanVerificationResult(valid=False, output="fail", error="type mismatch")
        assert r.valid is False
        assert "type mismatch" in r.error

    def test_frozen(self):
        r = LeanVerificationResult(valid=True, output="ok")
        with pytest.raises(AttributeError):
            r.valid = False  # type: ignore[misc]


class TestLeanVerifierNotInstalled:
    """Tests that work even without Lean installed."""

    def test_missing_lean_returns_error(self):
        v = LeanVerifier(lean_path="__nonexistent_lean_binary__")
        result = v.verify_raw("theorem x : True := trivial")
        assert result.valid is False
        assert result.error is not None
        assert "not found" in result.error.lower()


@pytest.mark.skipif(not is_lean_available(), reason="Lean 4 not installed")
class TestLeanVerifierWithLean:
    """Integration tests that require a working Lean 4 installation."""

    def test_valid_simple_proof(self):
        v = LeanVerifier(lean_path=_lean_path())
        code = "theorem test_rfl : 1 + 1 = 2 := by rfl"
        result = v.verify_raw(code)
        assert result.valid is True

    def test_invalid_proof(self):
        v = LeanVerifier(lean_path=_lean_path())
        code = "theorem bad : 1 + 1 = 3 := by rfl"
        result = v.verify_raw(code)
        assert result.valid is False

    def test_verify_with_header_and_tactics(self):
        v = LeanVerifier(lean_path=_lean_path())
        header = "theorem add_test : 1 + 1 = 2 := by"
        tactics = "rfl"
        result = v.verify(header, tactics)
        assert result.valid is True
