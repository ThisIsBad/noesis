"""Minimal agent integration example for LogicBrain.

Shows how an AI coding agent (Claude Code, OpenCode, Aider, etc.) can use
LogicBrain as a deterministic logic verification tool.  Copy-paste this into
your agent's tool execution environment to get started.

Workflow covered:
    1. Verify a user-provided argument           (string API)
    2. Generate a fresh problem + verify answer   (ProblemGenerator)
    3. Run an incremental Z3 session              (Z3Session)
    4. Inspect structured diagnostics             (Diagnostic)
    5. (Optional) Lean 4 tactic proof             (LeanSession)

Requirements:
    pip install -e ".[dev]"     # from the LogicBrain repo root
    # Lean 4 is optional — install via https://leanprover.github.io/lean4/doc/setup.html
"""

from __future__ import annotations

from logos import (
    Diagnostic,
    ErrorType,
    LeanSession,
    Z3Session,
    is_lean_available,
    verify,
)
from logos.generator import ProblemGenerator, EASY


# ---------------------------------------------------------------------------
# 1. Verify a user-provided argument (the most common agent action)
# ---------------------------------------------------------------------------

def step_verify_argument() -> None:
    """Agent decision point: user claims 'P -> Q, Q |- P' is valid."""

    result = verify("P -> Q, Q |- P")

    # -- Agent reads these fields to decide next action --
    if result.valid:
        print("[VERIFY] Argument is VALID.")
        print(f"  Rule: {result.rule}")
    else:
        print("[VERIFY] Argument is INVALID (fallacy detected).")
        print(f"  Rule:           {result.rule}")
        print(f"  Counterexample: {result.counterexample}")
        print(f"  Explanation:    {result.explanation}")
        # Agent action: inform the user that their reasoning is flawed,
        # citing the counterexample as evidence.


# ---------------------------------------------------------------------------
# 2. Generate a fresh problem and verify the agent's own answer
# ---------------------------------------------------------------------------

def step_generate_and_self_check() -> None:
    """Agent decision point: generate a problem to test its own reasoning."""

    gen = ProblemGenerator(EASY)
    problems = gen.generate_batch(1)
    problem = problems[0]

    print(f"\n[GENERATE] Problem {problem['id']}  [{problem['difficulty']}]")
    print(problem["natural_language"])

    # Agent would reason about the problem here and produce an answer.
    # For this example we pretend the agent answered "True".
    agent_answer = True

    # -- Ground-truth check (deterministic, Z3-backed) --
    correct = problem["ground_truth_valid"]
    if agent_answer == correct:
        print(f"  Agent answer: correct ({correct})")
    else:
        print(f"  Agent answer: WRONG (said {agent_answer}, truth is {correct})")
        print(f"  Rule: {problem['rule']}")
        # Agent action: log the mistake, adjust confidence, retry with
        # a different reasoning strategy.


# ---------------------------------------------------------------------------
# 3. Incremental Z3 session — constraint exploration
# ---------------------------------------------------------------------------

def step_z3_session() -> None:
    """Agent decision point: explore a constraint space incrementally."""

    session = Z3Session()
    session.declare("x", "Int")
    session.declare("y", "Int")

    session.assert_constraint("x > 0")
    session.assert_constraint("y > x")
    session.assert_constraint("x + y < 20")

    result = session.check()
    print(f"\n[Z3] Status: {result.status}")
    print(f"  Model: {result.model}")

    # Agent decides to tighten constraints via push/pop.
    session.push()
    session.assert_constraint("x > 15")

    result = session.check()
    print(f"  After x>15: {result.status}")

    if not result.satisfiable:
        # -- Structured diagnostics for the agent --
        print(f"  Error type:  {result.error_type}")
        print(f"  Suggestions: {result.suggestions}")
        # Agent action: relax constraints or report infeasibility.

    session.pop()  # undo x>15

    result = session.check()
    print(f"  After pop:   {result.status} (model={result.model})")


# ---------------------------------------------------------------------------
# 4. Inspect a Diagnostic object (agent-readable error metadata)
# ---------------------------------------------------------------------------

def step_diagnostics() -> None:
    """Agent decision point: structured error handling."""

    diag = Diagnostic(
        error_type=ErrorType.UNDECLARED_VARIABLE,
        message="Variable 'z' not declared",
        context="Z3Session.assert_constraint('z > 0')",
        suggestions=["Declare 'z' with session.declare('z', 'Int') first."],
    )

    print(f"\n[DIAG] error_type={diag.error_type.value}  schema_version={diag.schema_version}")
    print(f"  message:     {diag.message}")
    print(f"  context:     {diag.context}")
    print(f"  suggestions: {diag.suggestions}")
    # Agent action: follow the suggestion automatically — call
    # session.declare('z', 'Int'), then retry the constraint.


# ---------------------------------------------------------------------------
# 5. (Optional) Lean 4 tactic proof
# ---------------------------------------------------------------------------

def step_lean_session() -> None:
    """Agent decision point: build a formal proof tactic-by-tactic."""

    if not is_lean_available():
        print("\n[LEAN] Lean 4 not installed -- skipping.")
        print("  Install via: https://leanprover.github.io/lean4/doc/setup.html")
        return

    session = LeanSession()
    # start() may return success=False because Lean sees unsolved goals;
    # that is expected — the goals ARE the work to be done.
    session.start("theorem demo : True := by")

    result = session.apply("trivial")

    if result.success and session.is_complete:
        proof = session.proof or ""
        # Sanitise for terminals that lack full Unicode support (Windows cp1252)
        safe = proof.encode("ascii", "replace").decode()
        print("\n[LEAN] Proof complete!")
        print(f"  Proof:\n{safe}")
    elif not result.success:
        msg = (result.error_message or "unknown error").encode("ascii", "replace").decode()
        print(f"\n[LEAN] Tactic failed: {msg}")
        print(f"  Error type:  {result.error_type}")
        print(f"  Suggestions: {result.suggestions}")
        # Agent action: try a different tactic based on the suggestion.


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run all integration steps sequentially."""
    print("=" * 60)
    print("LogicBrain — Agent Integration Example")
    print("=" * 60)

    step_verify_argument()
    step_generate_and_self_check()
    step_z3_session()
    step_diagnostics()
    step_lean_session()

    print("\n" + "=" * 60)
    print("Done. All steps completed.")
    print("=" * 60)


if __name__ == "__main__":
    main()
