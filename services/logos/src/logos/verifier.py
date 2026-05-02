"""Deterministic propositional-logic verifier backed by Z3.

This is the "Gegenspieler" — it cannot *solve* problems, but it can
*verify* whether a conclusion follows necessarily from its premises.
Exploiting the P != NP asymmetry: verification is cheap, generation is hard.
"""

from __future__ import annotations

from typing import Union, cast

import z3

from logos.models import (
    Argument,
    Connective,
    LogicalExpression,
    Proposition,
    VerificationResult,
)

# Type alias for expression nodes
Expr = Union[Proposition, LogicalExpression]


class PropositionalVerifier:
    """Z3-backed verifier for propositional logic arguments.

    Usage
    -----
    >>> v = PropositionalVerifier()
    >>> result = v.verify(argument)
    >>> print(result)        # VALID - [Modus Ponens] ...
    """

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def verify(self, argument: Argument) -> VerificationResult:
        """Check whether *argument.conclusion* follows necessarily from
        *argument.premises*.

        The algorithm:
        1. Collect all atomic propositions.
        2. Create a Z3 Boolean variable for each.
        3. Assert all premises as constraints.
        4. Assert the **negation** of the conclusion.
        5. If UNSAT -> the conclusion is a *logical consequence* (valid).
           If SAT -> the model is a *counterexample* (invalid).
        """
        # Gather atoms and create Z3 variables
        atoms = self._collect_atoms(argument)
        z3_vars: dict[str, z3.BoolRef] = {label: z3.Bool(label) for label in sorted(atoms)}

        solver = z3.Solver()

        # Assert all premises
        for premise in argument.premises:
            solver.add(self._to_z3(premise, z3_vars))

        # Assert the NEGATION of the conclusion
        solver.add(z3.Not(self._to_z3(argument.conclusion, z3_vars)))

        result = solver.check()

        if result == z3.unsat:
            # No counterexample exists -> conclusion follows necessarily
            rule = self._identify_rule(argument)
            return VerificationResult(
                valid=True,
                counterexample=None,
                rule=rule,
                explanation=(
                    "The conclusion follows necessarily from the premises. "
                    "No truth-value assignment can make all premises true "
                    "while making the conclusion false."
                ),
            )
        elif result == z3.sat:
            # Counterexample found
            model = solver.model()
            counterexample = {label: bool(model.evaluate(var, model_completion=True)) for label, var in z3_vars.items()}
            fallacy = self._identify_fallacy(argument)
            return VerificationResult(
                valid=False,
                counterexample=counterexample,
                rule=fallacy,
                explanation=(
                    "The conclusion does NOT follow from the premises. "
                    f"Counterexample: when {self._format_counterexample(counterexample)}, "
                    "all premises are true but the conclusion is false."
                ),
            )
        else:
            # z3.unknown — should not happen for propositional logic
            return VerificationResult(
                valid=False,
                rule="UNKNOWN",
                explanation="Z3 returned 'unknown' - this is unexpected for propositional logic.",
            )

    def check_equivalence(
        self,
        expr_a: Expr,
        expr_b: Expr,
    ) -> VerificationResult:
        """Check whether two expressions are logically equivalent."""
        # A <-> B is valid iff NOT(A <-> B) is unsatisfiable
        iff = LogicalExpression(Connective.IFF, expr_a, expr_b)
        arg = Argument(premises=[], conclusion=iff)
        result = self.verify(arg)
        if result.valid:
            return VerificationResult(
                valid=True,
                rule="Logical Equivalence",
                explanation=f"{expr_a} is logically equivalent to {expr_b}.",
            )
        return VerificationResult(
            valid=False,
            counterexample=result.counterexample,
            rule="Not Equivalent",
            explanation=f"{expr_a} is NOT logically equivalent to {expr_b}.",
        )

    def is_tautology(self, expr: Expr) -> VerificationResult:
        """Check whether an expression is a tautology (always true)."""
        arg = Argument(premises=[], conclusion=expr)
        return self.verify(arg)

    def is_contradiction(self, expr: Expr) -> VerificationResult:
        """Check whether an expression is a contradiction (always false)."""
        neg = LogicalExpression(Connective.NOT, expr)
        result = self.is_tautology(neg)
        if result.valid:
            return VerificationResult(
                valid=True,
                rule="Contradiction",
                explanation=f"{expr} is a contradiction - it is false under every assignment.",
            )
        return VerificationResult(
            valid=False,
            rule="Not a Contradiction",
            explanation=f"{expr} is NOT a contradiction.",
        )

    # -----------------------------------------------------------------
    # Z3 translation
    # -----------------------------------------------------------------

    def _to_z3(
        self,
        expr: Expr,
        z3_vars: dict[str, z3.BoolRef],
    ) -> z3.BoolRef:
        """Recursively translate a logic expression into a Z3 formula."""
        if isinstance(expr, Proposition):
            return z3_vars[expr.label]

        if not isinstance(expr, LogicalExpression):
            raise TypeError(f"Unexpected type: {type(expr)}")

        left = self._to_z3(expr.left, z3_vars)

        if expr.connective is Connective.NOT:
            return cast(z3.BoolRef, z3.Not(left))

        if expr.right is None:
            raise ValueError(f"Binary connective {expr.connective} requires right operand")

        right = self._to_z3(expr.right, z3_vars)

        if expr.connective is Connective.AND:
            return cast(z3.BoolRef, z3.And(left, right))
        elif expr.connective is Connective.OR:
            return cast(z3.BoolRef, z3.Or(left, right))
        elif expr.connective is Connective.IMPLIES:
            return cast(z3.BoolRef, z3.Implies(left, right))
        elif expr.connective is Connective.IFF:
            return cast(z3.BoolRef, left == right)
        else:
            raise ValueError(f"Unknown connective: {expr.connective}")

    # -----------------------------------------------------------------
    # Atom collection
    # -----------------------------------------------------------------

    def _collect_atoms(self, argument: Argument) -> set[str]:
        """Return the set of all atomic proposition labels in an argument."""
        atoms: set[str] = set()
        for premise in argument.premises:
            self._collect_atoms_from_expr(premise, atoms)
        self._collect_atoms_from_expr(argument.conclusion, atoms)
        return atoms

    def _collect_atoms_from_expr(
        self,
        expr: Expr,
        atoms: set[str],
    ) -> None:
        if isinstance(expr, Proposition):
            atoms.add(expr.label)
        elif isinstance(expr, LogicalExpression):
            self._collect_atoms_from_expr(expr.left, atoms)
            if expr.right is not None:
                self._collect_atoms_from_expr(expr.right, atoms)

    # -----------------------------------------------------------------
    # Rule / fallacy identification (heuristic pattern matching)
    # -----------------------------------------------------------------

    def _identify_rule(self, argument: Argument) -> str:
        """Try to identify which inference rule makes this argument valid."""
        prems = argument.premises
        conc = argument.conclusion

        # Modus Ponens: P, P->Q |- Q
        for i, p1 in enumerate(prems):
            for j, p2 in enumerate(prems):
                if i == j:
                    continue
                if isinstance(p2, LogicalExpression) and p2.connective is Connective.IMPLIES and p2.right is not None:
                    if self._expr_eq(p2.left, p1) and self._expr_eq(p2.right, conc):
                        return "Modus Ponens"

        # Modus Tollens: P->Q, ~Q |- ~P
        for i, p1 in enumerate(prems):
            if isinstance(p1, LogicalExpression) and p1.connective is Connective.IMPLIES and p1.right is not None:
                neg_right = LogicalExpression(Connective.NOT, p1.right)
                neg_left = LogicalExpression(Connective.NOT, p1.left)
                for j, p2 in enumerate(prems):
                    if i == j:
                        continue
                    if self._expr_eq(p2, neg_right) and self._expr_eq(conc, neg_left):
                        return "Modus Tollens"

        # Hypothetical Syllogism: P->Q, Q->R |- P->R
        if isinstance(conc, LogicalExpression) and conc.connective is Connective.IMPLIES and conc.right is not None:
            for i, p1 in enumerate(prems):
                for j, p2 in enumerate(prems):
                    if i == j:
                        continue
                    if (
                        isinstance(p1, LogicalExpression)
                        and p1.connective is Connective.IMPLIES
                        and p1.right is not None
                        and isinstance(p2, LogicalExpression)
                        and p2.connective is Connective.IMPLIES
                        and p2.right is not None
                    ):
                        if (
                            self._expr_eq(p1.left, conc.left)
                            and self._expr_eq(p1.right, p2.left)
                            and self._expr_eq(p2.right, conc.right)
                        ):
                            return "Hypothetical Syllogism"

        # Disjunctive Syllogism: P|Q, ~P |- Q
        for i, p1 in enumerate(prems):
            if isinstance(p1, LogicalExpression) and p1.connective is Connective.OR and p1.right is not None:
                for j, p2 in enumerate(prems):
                    if i == j:
                        continue
                    neg_left = LogicalExpression(Connective.NOT, p1.left)
                    neg_right = LogicalExpression(Connective.NOT, p1.right)
                    if self._expr_eq(p2, neg_left) and self._expr_eq(conc, p1.right):
                        return "Disjunctive Syllogism"
                    if self._expr_eq(p2, neg_right) and self._expr_eq(conc, p1.left):
                        return "Disjunctive Syllogism"

        # Contraposition: P->Q |- ~Q->~P
        if len(prems) == 1:
            p = prems[0]
            if (
                isinstance(p, LogicalExpression)
                and p.connective is Connective.IMPLIES
                and p.right is not None
                and isinstance(conc, LogicalExpression)
                and conc.connective is Connective.IMPLIES
                and conc.right is not None
            ):
                neg_q = LogicalExpression(Connective.NOT, p.right)
                neg_p = LogicalExpression(Connective.NOT, p.left)
                if self._expr_eq(conc.left, neg_q) and self._expr_eq(conc.right, neg_p):
                    return "Contraposition"

        return "Valid (rule not identified)"

    def _identify_fallacy(self, argument: Argument) -> str:
        """Try to identify which fallacy makes this argument invalid."""
        prems = argument.premises
        conc = argument.conclusion

        # Affirming the Consequent: P->Q, Q |- P  (INVALID)
        for i, p1 in enumerate(prems):
            if isinstance(p1, LogicalExpression) and p1.connective is Connective.IMPLIES and p1.right is not None:
                for j, p2 in enumerate(prems):
                    if i == j:
                        continue
                    if self._expr_eq(p2, p1.right) and self._expr_eq(conc, p1.left):
                        return "Affirming the Consequent (fallacy)"

        # Denying the Antecedent: P->Q, ~P |- ~Q  (INVALID)
        for i, p1 in enumerate(prems):
            if isinstance(p1, LogicalExpression) and p1.connective is Connective.IMPLIES and p1.right is not None:
                neg_left = LogicalExpression(Connective.NOT, p1.left)
                neg_right = LogicalExpression(Connective.NOT, p1.right)
                for j, p2 in enumerate(prems):
                    if i == j:
                        continue
                    if self._expr_eq(p2, neg_left) and self._expr_eq(conc, neg_right):
                        return "Denying the Antecedent (fallacy)"

        return "Invalid (fallacy not identified)"

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def _expr_eq(self, a: Expr, b: Expr) -> bool:
        """Structural equality check (not semantic equivalence)."""
        if type(a) is not type(b):
            return False
        if isinstance(a, Proposition) and isinstance(b, Proposition):
            return a.label == b.label
        if isinstance(a, LogicalExpression) and isinstance(b, LogicalExpression):
            if a.connective != b.connective:
                return False
            if not self._expr_eq(a.left, b.left):
                return False
            if a.right is None and b.right is None:
                return True
            if a.right is None or b.right is None:
                return False
            return self._expr_eq(a.right, b.right)
        return False

    @staticmethod
    def _format_counterexample(ce: dict[str, bool]) -> str:
        parts = [f"{k}={'T' if v else 'F'}" for k, v in sorted(ce.items())]
        return ", ".join(parts)
