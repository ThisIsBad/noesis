"""Interactive Lean 4 session wrapper for tactic-by-tactic proving.

This module provides a REPL-like interface to Lean 4, allowing agents
to build proofs incrementally with immediate feedback after each tactic.

Example
-------
>>> from logos import LeanSession
>>> session = LeanSession()
>>> session.start("theorem test : 1 + 1 = 2 := by")
>>> print(session.goals)  # ['⊢ 1 + 1 = 2']
>>> result = session.apply("rfl")
>>> print(result.success)  # True
>>> print(session.is_complete)  # True
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from logos.diagnostics import Diagnostic


@dataclass
class TacticResult:
    """Result of applying a tactic.
    
    Attributes
    ----------
    success : bool
        Whether the tactic was accepted by Lean.
    goals : list[str]
        List of remaining goals after the tactic.
    proof_so_far : str
        The complete proof text so far.
    error_message : str, optional
        Error message if the tactic failed.
    diagnostic : Diagnostic, optional
        Structured diagnostic information for errors.
    """

    success: bool
    """Whether the tactic was accepted by Lean."""

    goals: list[str]
    """List of remaining goals after the tactic."""

    proof_so_far: str
    """The complete proof text so far."""

    error_message: Optional[str] = None
    """Error message if the tactic failed."""

    diagnostic: Optional["Diagnostic"] = None
    """Structured diagnostic information (error type, suggestions, etc.)."""

    @property
    def error_type(self) -> Optional[str]:
        """Shortcut to diagnostic.error_type.value."""
        if self.diagnostic:
            return self.diagnostic.error_type.value
        return None

    @property
    def suggestions(self) -> list[str]:
        """Shortcut to diagnostic.suggestions."""
        if self.diagnostic:
            return self.diagnostic.suggestions
        return []


@dataclass
class LeanSession:
    """Interactive Lean 4 session for incremental proof construction.
    
    This class simulates a REPL by writing the proof iteratively to a 
    temporary file and parsing the Lean compiler output. This approach
    is more robust than trying to interact with the LSP server directly.
    
    Parameters
    ----------
    lean_path : str, optional
        Path to the Lean 4 executable. If not provided, will try to
        find it automatically via `elan` or system PATH.
    timeout : int, optional
        Timeout in seconds for Lean compiler calls. Default is 30.
    
    Example
    -------
    >>> session = LeanSession()
    >>> session.start("theorem foo : True := by")
    >>> result = session.apply("trivial")
    >>> assert session.is_complete
    """

    lean_path: Optional[str] = None
    timeout: int = 60

    # Internal state
    _header: str = field(default="", init=False)
    _tactics: list[str] = field(default_factory=list, init=False)
    _goals: list[str] = field(default_factory=list, init=False)
    _is_complete: bool = field(default=False, init=False)
    _initialized: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """Find Lean executable if not provided."""
        if self.lean_path is None:
            self.lean_path = self._find_lean()

    @staticmethod
    def _find_lean() -> str:
        """Try to find the Lean 4 executable."""
        # Try common locations
        candidates = [
            shutil.which("lean"),  # System PATH
            shutil.which("lake"),  # Lake might be in PATH
        ]

        # Windows: Check elan default location
        if os.name == 'nt':
            home = os.environ.get('USERPROFILE', '')
            elan_lean = os.path.join(home, '.elan', 'bin', 'lean.exe')
            if os.path.exists(elan_lean):
                candidates.append(elan_lean)
        else:
            # Unix: Check elan default location
            home = os.environ.get('HOME', '')
            elan_lean = os.path.join(home, '.elan', 'bin', 'lean')
            if os.path.exists(elan_lean):
                candidates.append(elan_lean)

        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return candidate

        raise FileNotFoundError(
            "Could not find Lean 4 executable. Please install Lean 4 via elan "
            "(https://elan.leanprover.org) or provide the path explicitly."
        )

    @property
    def goals(self) -> list[str]:
        """Current list of open goals."""
        return self._goals.copy()

    @property
    def is_complete(self) -> bool:
        """Whether the proof is complete (no remaining goals)."""
        return self._is_complete

    @property
    def proof(self) -> str:
        """The complete proof text so far."""
        lines = [self._header]
        for tactic in self._tactics:
            lines.append(f"  {tactic}")
        return "\n".join(lines)

    def start(self, theorem_header: str) -> TacticResult:
        """Start a new proof session.
        
        Parameters
        ----------
        theorem_header : str
            The theorem statement with `by` keyword.
            Example: "theorem foo (n : Nat) : n = n := by"
        
        Returns
        -------
        TacticResult
            Initial state with the goals to prove.
        """
        self._header = theorem_header.strip()
        self._tactics = []
        self._is_complete = False
        self._initialized = True

        # Check initial state
        result = self._check_state()
        self._goals = result.goals

        return result

    def apply(self, tactic: str) -> TacticResult:
        """Apply a tactic to the current proof state.
        
        Parameters
        ----------
        tactic : str
            The tactic to apply, e.g., "rfl", "simp", "intro h".
        
        Returns
        -------
        TacticResult
            The result of applying the tactic. If successful, the
            internal state is updated. If failed, state is unchanged.
        """
        if not self._initialized:
            raise RuntimeError("Session not started. Call start() first.")

        if self._is_complete:
            return TacticResult(
                success=False,
                goals=[],
                proof_so_far=self.proof,
                error_message="Proof is already complete."
            )

        # Temporarily add the tactic
        tactic_stripped = tactic.strip()
        self._tactics.append(tactic_stripped)

        # Check if it works
        result = self._check_state(current_tactic=tactic_stripped)

        if result.success:
            self._goals = result.goals
            if not self._goals:
                self._is_complete = True
            return result
        else:
            # Revert on failure
            self._tactics.pop()
            return result

    def undo(self) -> TacticResult:
        """Undo the last tactic.
        
        Returns
        -------
        TacticResult
            The state after undoing.
        """
        if not self._tactics:
            return TacticResult(
                success=False,
                goals=self._goals,
                proof_so_far=self.proof,
                error_message="No tactics to undo."
            )

        self._tactics.pop()
        self._is_complete = False

        result = self._check_state()
        self._goals = result.goals
        return result

    def reset(self) -> None:
        """Reset the session, clearing all state."""
        self._header = ""
        self._tactics = []
        self._goals = []
        self._is_complete = False
        self._initialized = False

    def _check_state(self, current_tactic: Optional[str] = None) -> TacticResult:
        """Run Lean on the current proof and parse the output."""
        proof_text = self.proof

        # Create a temporary file
        fd, temp_path = tempfile.mkstemp(suffix='.lean', prefix='logos_')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(proof_text)

            # Run Lean compiler
            try:
                if self.lean_path is None:
                    raise RuntimeError("Lean path not set")
                cmd = [self.lean_path, temp_path]
                process = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    timeout=self.timeout
                )
                output = process.stdout + process.stderr
                return self._parse_output(output, proof_text, current_tactic)

            except subprocess.TimeoutExpired:
                from logos.diagnostics import Diagnostic, ErrorType
                return TacticResult(
                    success=False,
                    goals=self._goals,
                    proof_so_far=proof_text,
                    error_message=f"Lean timed out after {self.timeout} seconds.",
                    diagnostic=Diagnostic(
                        error_type=ErrorType.TIMEOUT,
                        message=f"Lean timed out after {self.timeout} seconds",
                        suggestions=["Try a simpler tactic", "Increase timeout if needed"],
                    )
                )
            except FileNotFoundError:
                from logos.diagnostics import Diagnostic, ErrorType
                return TacticResult(
                    success=False,
                    goals=self._goals,
                    proof_so_far=proof_text,
                    error_message=f"Lean executable not found at: {self.lean_path}",
                    diagnostic=Diagnostic(
                        error_type=ErrorType.INTERNAL_ERROR,
                        message=f"Lean executable not found at: {self.lean_path}",
                        suggestions=["Install Lean 4 via elan", "Check lean_path parameter"],
                    )
                )
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def _parse_output(
        self,
        output: str,
        proof_text: str,
        current_tactic: Optional[str] = None
    ) -> TacticResult:
        """Parse Lean compiler output to extract goals and errors."""
        output_lower = output.lower()

        # Check for errors
        if "error:" in output_lower:
            # Extract the error message
            error_lines: list[str] = []
            for line in output.split('\n'):
                if 'error:' in line.lower() or (error_lines and line.strip()):
                    error_lines.append(line)
                    if len(error_lines) > 5:  # Limit error length
                        break

            error_message = '\n'.join(error_lines).strip() or output.strip()

            # Parse into structured diagnostic
            from logos.diagnostics import LeanDiagnosticParser
            diagnostic = LeanDiagnosticParser.parse(output, current_tactic)

            return TacticResult(
                success=False,
                goals=self._goals,
                proof_so_far=proof_text,
                error_message=error_message,
                diagnostic=diagnostic,
            )

        # Check for unsolved goals
        goals = []
        if "unsolved goals" in output_lower:
            goals = self._extract_goals(output)
            return TacticResult(
                success=True,
                goals=goals if goals else ["(could not parse goal state)"],
                proof_so_far=proof_text
            )

        # No errors and no unsolved goals = proof complete
        return TacticResult(
            success=True,
            goals=[],
            proof_so_far=proof_text
        )

    def _extract_goals(self, output: str) -> list[str]:
        """Extract goal states from Lean output.
        
        Lean 4 formats goals like:
            unsolved goals
            case ...
            a b : Nat
            ⊢ a + b = b + a
        """
        goals = []
        lines = output.split('\n')
        current_goal: list[str] = []
        capturing = False

        for line in lines:
            if "unsolved goals" in line.lower():
                capturing = True
                continue

            if capturing:
                # Empty line might separate multiple goals
                if line.strip() == "" and current_goal:
                    goal_text = '\n'.join(current_goal).strip()
                    if goal_text:
                        goals.append(goal_text)
                    current_goal = []
                elif line.strip():
                    # Skip file path lines like "temp.lean:1:2:"
                    if not (line.strip().endswith(':') and ':' in line):
                        current_goal.append(line)

        # Don't forget the last goal
        if current_goal:
            goal_text = '\n'.join(current_goal).strip()
            if goal_text:
                goals.append(goal_text)

        return goals


def is_lean_available() -> bool:
    """Check if Lean 4 is available on this system."""
    try:
        LeanSession._find_lean()
        return True
    except FileNotFoundError:
        return False
