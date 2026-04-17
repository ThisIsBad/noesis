"""Examples for LeanSession and Z3Session interactive workflows."""

from logos import LeanSession, Z3Session, is_lean_available


def run_lean_session() -> None:
    if not is_lean_available():
        print("Lean 4 not available. Skipping LeanSession example.")
        return

    session = LeanSession()
    start = session.start("theorem test : 1 + 1 = 2 := by")
    if not start.success:
        print("Lean start warning:", start.error_message)

    result = session.apply("rfl")
    print("Lean success:", result.success)
    print("Lean complete:", session.is_complete)


def run_z3_session() -> None:
    session = Z3Session(track_unsat_core=True)
    session.declare("x", "Int")
    session.assert_constraint("x > 0", name="positive")
    session.assert_constraint("x < 0", name="negative")

    result = session.check()
    print("Z3 status:", result.status)
    print("Z3 satisfiable:", result.satisfiable)
    print("Z3 error_type:", result.error_type)
    print("Z3 suggestions:", result.suggestions)


def main() -> None:
    run_lean_session()
    run_z3_session()


if __name__ == "__main__":
    main()
