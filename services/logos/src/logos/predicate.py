"""Z3-backed deterministic verifier for First-Order Logic (Predicate Logic)."""

from __future__ import annotations

from typing import Any, cast

import z3

from logos.models import VerificationResult
from logos.predicate_models import (
    Variable, Constant, Predicate, PredicateConnective,
    PredicateExpression, QuantifiedExpression, Quantifier, FOLArgument
)


class PredicateVerifier:
    """Verifies First-Order Logic arguments using the Z3 SMT solver."""

    def __init__(self) -> None:
        # We use a single domain of discourse (Universe of Discourse)
        self.U: z3.SortRef = z3.DeclareSort('U')
        # Cache for Z3 constants, variables, and predicates so they remain consistent across the argument
        self.z3_constants: dict[str, z3.ExprRef] = {}
        self.z3_predicates: dict[str, z3.FuncDeclRef] = {}

    def _reset_cache(self) -> None:
        """Clears the cache for a new verification run."""
        self.z3_constants.clear()
        self.z3_predicates.clear()

    def _get_z3_constant(self, name: str) -> z3.ExprRef:
        """Get or create a Z3 constant in the universe of discourse."""
        if name not in self.z3_constants:
            self.z3_constants[name] = cast(z3.ExprRef, z3.Const(name, self.U))
        return self.z3_constants[name]

    def _get_z3_predicate(self, name: str, arity: int) -> z3.FuncDeclRef:
        """Get or create an uninterpreted relation (predicate) taking 'arity' elements from U."""
        if name not in self.z3_predicates:
            domain = [self.U] * arity
            self.z3_predicates[name] = z3.Function(name, *domain, z3.BoolSort())
        return self.z3_predicates[name]

    def _convert(self, expr: Any, var_env: dict[str, z3.ExprRef]) -> z3.ExprRef:
        """Translates a FOLFormula AST into a Z3 expression recursively."""

        if isinstance(expr, Predicate):
            z3_terms: list[z3.ExprRef] = []
            for term in expr.terms:
                if isinstance(term, Variable):
                    if term.name in var_env:
                        z3_terms.append(var_env[term.name])
                    else:
                        raise ValueError(f"Unbound variable: {term.name}")
                elif isinstance(term, Constant):
                    z3_terms.append(self._get_z3_constant(term.name))
                else:
                    raise ValueError(f"Unknown term type: {type(term)}")

            z3_pred = self._get_z3_predicate(expr.name, len(expr.terms))
            return z3_pred(*z3_terms)

        elif isinstance(expr, PredicateExpression):
            left_z3 = self._convert(expr.left, var_env)
            if expr.connective == PredicateConnective.NOT:
                return cast(z3.ExprRef, z3.Not(left_z3))

            if expr.right is None:
                raise ValueError("Binary connective requires right operand")

            right_z3 = self._convert(expr.right, var_env)
            if expr.connective == PredicateConnective.AND:
                return cast(z3.ExprRef, z3.And(left_z3, right_z3))
            elif expr.connective == PredicateConnective.OR:
                return cast(z3.ExprRef, z3.Or(left_z3, right_z3))
            elif expr.connective == PredicateConnective.IMPLIES:
                return cast(z3.ExprRef, z3.Implies(left_z3, right_z3))
            elif expr.connective == PredicateConnective.IFF:
                return cast(z3.ExprRef, left_z3 == right_z3)

        elif isinstance(expr, QuantifiedExpression):
            # Create a fresh bound variable for Z3
            # In Z3, quantified variables are also just z3.Const but inside of a z3.ForAll
            bound_var = z3.Const(expr.variable.name, self.U)

            # Create a new environment extending the old one with the bound variable
            new_env = var_env.copy()
            new_env[expr.variable.name] = bound_var

            inside_expr = self._convert(expr.expression, new_env)

            if expr.quantifier == Quantifier.FORALL:
                return z3.ForAll([bound_var], inside_expr)
            elif expr.quantifier == Quantifier.EXISTS:
                return z3.Exists([bound_var], inside_expr)

        raise ValueError(f"Unsupported expression type: {type(expr)}")

    def verify(self, argument: FOLArgument) -> VerificationResult:
        """
        Verifies if the conclusion logically follows from the premises.
        Uses Proof by Refutation: Premise1 AND Premise2 AND ... AND NOT(Conclusion)
        If this is UNSAT, the argument is valid.
        """
        self._reset_cache()
        solver = z3.Solver()

        # 1. Provide all premises to the solver
        try:
            for p in argument.premises:
                z3_p = self._convert(p, {})
                solver.add(z3_p)

            # 2. Negate the conclusion
            z3_c = self._convert(argument.conclusion, {})
            # We want to check P1 ^ P2 ^ ... ^ ~C
            solver.add(z3.Not(z3_c))

            # 3. Check satisfiability of the negation
            result = solver.check()

            if result == z3.unsat:
                return VerificationResult(
                    valid=True,
                    counterexample=None,
                    rule="Valid (Predicate logic valid)",
                    explanation="The conclusion necessarily follows. No counterexample exists."
                )
            elif result == z3.sat:
                model = solver.model()
                # Extracting a readable counterexample from Z3 models with uninterpreted sorts is tricky
                # Z3 will create U!val!0, U!val!1 etc. We will return the raw string representation of the model for now
                ce_repr = str(model)
                return VerificationResult(
                    valid=False,
                    counterexample={"raw_model": ce_repr},
                    rule="Invalid (Predicate logic counterexample)",
                    explanation="Found a counterexample where all premises are true but the conclusion is false."
                )
            else:
                return VerificationResult(
                    valid=False,
                    counterexample=None,
                    rule="Unknown",
                    explanation=f"Z3 solver returned unknown. Reason: {solver.reason_unknown()}"
                )
        except (z3.Z3Exception, ValueError, TypeError, KeyError) as e:
            return VerificationResult(
                valid=False,
                counterexample=None,
                rule="Error",
                explanation=f"Translation or solver error: {str(e)}"
            )
