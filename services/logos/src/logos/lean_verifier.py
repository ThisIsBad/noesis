"""Lean 4 Verification Backend.

Internal module — not part of the public API (Tier 3).
"""

__all__ = ["LeanVerifier", "LeanVerificationResult"]

import os
import tempfile
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class LeanVerificationResult:
    """Result of verifying a Lean 4 theorem."""

    valid: bool
    output: str
    error: str | None = None


class LeanVerifier:
    """Verifies mathematical proofs using the Lean 4 interactive theorem prover."""

    def __init__(self, lean_path: str = "lean", timeout: int = 60):
        # Allow passing the explicit path to the lean executable if it's not in global PATH
        self.lean_path = lean_path
        self.timeout = timeout

    def verify(self, theorem_header: str, tactic_proof: str) -> LeanVerificationResult:
        """
        Synthesizes a full .lean document, runs it through the Lean 4 compiler,
        and parses the result.

        Args:
            theorem_header: The theorem statement, e.g.
                ``theorem sum_even (a b : Nat) ... : Even (a + b) := by``
            tactic_proof: The generated tactics to prove the theorem.

        Returns:
            LeanVerificationResult containing whether the proof was successful.
        """
        full_code = f"{theorem_header}\n"
        # Indent the tactic proof appropriately
        for line in tactic_proof.strip().split("\n"):
            full_code += f"  {line.lstrip()}\n"

        return self.verify_raw(full_code)

    def verify_raw(self, full_lean_code: str) -> LeanVerificationResult:
        """Runs the Lean compiler on a raw string of Lean code."""
        # Create a temporary file
        fd, temp_path = tempfile.mkstemp(suffix=".lean")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                # Basic Mathlib imports might be needed depending on the theorems.
                # For now, we assume simple theorems that don't need heavy imports,
                # or the LLM includes `import Mathlib` at the top.
                f.write(full_lean_code)

            # Run lean compiler
            process = subprocess.run(
                [self.lean_path, temp_path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout,
            )

            output = process.stdout + process.stderr

            # In Lean 4, if there are unsolved goals or errors, the exit code is non-zero
            if process.returncode == 0 and "error:" not in output.lower():
                return LeanVerificationResult(valid=True, output=output, error=None)
            else:
                return LeanVerificationResult(valid=False, output=output, error="Proof failed. See compiler output.")

        except FileNotFoundError:
            return LeanVerificationResult(
                valid=False,
                output="",
                error=f"Lean executable not found at '{self.lean_path}'. Please ensure Lean 4 (elan) is installed.",
            )
        except subprocess.TimeoutExpired as e:
            return LeanVerificationResult(
                valid=False,
                output="",
                error=f"Lean timed out after {self.timeout} seconds: {str(e)}",
            )
        except (OSError, subprocess.SubprocessError) as e:
            return LeanVerificationResult(valid=False, output="", error=f"Error running Lean: {str(e)}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
