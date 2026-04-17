"""Minimal quick verification examples for propositional logic."""

from logos import are_equivalent, is_tautology, verify


def main() -> None:
    print("== Argument verification ==")
    result = verify("P -> Q, P |- Q")
    print(f"valid={result.valid}")
    print(f"rule={result.rule}")

    print("\n== Fallacy detection ==")
    result = verify("P -> Q, Q |- P")
    print(f"valid={result.valid}")
    print(f"rule={result.rule}")
    print(f"counterexample={result.counterexample}")

    print("\n== Tautology / equivalence checks ==")
    print("is_tautology('P | ~P') ->", is_tautology("P | ~P").valid)
    print(
        "are_equivalent('P -> Q', '~Q -> ~P') ->",
        are_equivalent("P -> Q", "~Q -> ~P").valid,
    )


if __name__ == "__main__":
    main()
