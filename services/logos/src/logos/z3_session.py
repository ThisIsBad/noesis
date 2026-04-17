"""Interactive Z3 session for incremental constraint solving.

This module provides a stateful interface to Z3, allowing agents to
build up constraint sets incrementally with push/pop for backtracking.

Example
-------
>>> from logos import Z3Session
>>> session = Z3Session()
>>> session.declare("x", "Int")
>>> session.declare("y", "Int")
>>> session.assert_constraint("x > 0")
>>> session.assert_constraint("y > x")
>>> result = session.check()
>>> print(result.satisfiable)  # True
>>> print(result.model)        # {'x': 1, 'y': 2}
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional, cast

import z3

from logos.exceptions import ConstraintError

if TYPE_CHECKING:
    from logos.diagnostics import Diagnostic


@dataclass
class CheckResult:
    """Result of a satisfiability check."""

    status: str
    """One of 'sat', 'unsat', or 'unknown'."""

    satisfiable: Optional[bool]
    """True if sat, False if unsat, None if unknown."""

    model: Optional[dict[str, Any]] = None
    """Variable assignments if satisfiable."""

    unsat_core: Optional[list[str]] = None
    """Named constraints in the unsat core (if tracking enabled)."""

    reason: Optional[str] = None
    """Reason for unknown result, if applicable."""

    diagnostic: Optional["Diagnostic"] = None
    """Structured diagnostic information for unsat/unknown/errors."""

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
class Z3Session:
    """Interactive Z3 session for incremental constraint solving.
    
    This class wraps Z3's incremental solving capabilities, providing:
    - Variable declaration with type inference
    - Constraint assertion with optional naming
    - Push/pop for backtracking (exploration of different branches)
    - Model extraction for satisfiable results
    - Unsat core extraction for debugging
    
    Example
    -------
    >>> session = Z3Session()
    >>> session.declare("x", "Int")
    >>> session.assert_constraint("x > 5")
    >>> session.assert_constraint("x < 3")
    >>> result = session.check()
    >>> print(result.satisfiable)  # False
    """

    timeout_ms: int = 30000
    """Timeout for solver in milliseconds."""

    track_unsat_core: bool = False
    """Whether to track assertions for unsat core extraction."""

    # Internal state
    _solver: z3.Solver = field(default_factory=z3.Solver, init=False)
    _variables: dict[str, z3.ExprRef] = field(default_factory=dict, init=False)
    _assertions: list[str] = field(default_factory=list, init=False)
    _assertion_names: dict[str, z3.BoolRef] = field(default_factory=dict, init=False)
    _scope_depth: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        """Initialize the solver with settings."""
        self._solver = z3.Solver()
        self._solver.set("timeout", self.timeout_ms)
        if self.track_unsat_core:
            self._solver.set("unsat_core", True)

    def declare(
        self,
        name: str,
        sort: str,
        size: Optional[int] = None
    ) -> None:
        """Declare a variable with the given name and sort.
        
        Parameters
        ----------
        name : str
            Variable name (must be valid identifier).
        sort : str
            Type of variable: "Int", "Real", "Bool", or "BitVec".
        size : int, optional
            Bit width for BitVec sort.
        
        Raises
        ------
        ValueError
            If the sort is unknown or BitVec without size.
        
        Example
        -------
        >>> session.declare("x", "Int")
        >>> session.declare("flag", "Bool")
        >>> session.declare("bits", "BitVec", size=32)
        """
        if name in self._variables:
            raise ValueError(f"Variable '{name}' already declared")

        sort_upper = sort.upper()

        if sort_upper == "INT":
            self._variables[name] = z3.Int(name)
        elif sort_upper == "REAL":
            self._variables[name] = z3.Real(name)
        elif sort_upper == "BOOL":
            self._variables[name] = z3.Bool(name)
        elif sort_upper == "BITVEC":
            if size is None:
                raise ValueError("BitVec requires size parameter")
            self._variables[name] = z3.BitVec(name, size)
        else:
            raise ValueError(
                f"Unknown sort '{sort}'. Supported: Int, Real, Bool, BitVec"
            )

    def assert_constraint(
        self,
        constraint: str,
        name: Optional[str] = None
    ) -> None:
        """Assert a constraint in the current scope.
        
        Parameters
        ----------
        constraint : str
            Constraint expression using declared variables.
            Supports: +, -, *, /, >, <, >=, <=, ==, !=, and, or, not, =>
        name : str, optional
            Name for tracking in unsat core.
        
        Example
        -------
        >>> session.assert_constraint("x > 0")
        >>> session.assert_constraint("x + y == 10", name="sum_constraint")
        """
        try:
            expr = self._parse_constraint(constraint)
        except (ValueError, ConstraintError) as exc:
            from logos.diagnostics import Z3DiagnosticParser

            diagnostic = Z3DiagnosticParser.parse_constraint_error(str(exc), constraint)
            raise ConstraintError(str(diagnostic)) from exc

        if self.track_unsat_core and name:
            # Create a named assertion for unsat core tracking
            indicator = z3.Bool(f"__track_{name}")
            self._assertion_names[name] = indicator
            self._solver.add(z3.Implies(indicator, expr))
            self._solver.add(indicator)
        else:
            self._solver.add(expr)

        self._assertions.append(constraint)

    def check(self) -> CheckResult:
        """Check satisfiability of current constraints.
        
        Returns
        -------
        CheckResult
            Result containing status, model (if sat), or unsat core.
        """
        result = self._solver.check()

        if result == z3.sat:
            model = self._solver.model()
            model_dict = self._extract_model(model)
            return CheckResult(
                status="sat",
                satisfiable=True,
                model=model_dict
            )
        elif result == z3.unsat:
            from logos.diagnostics import Z3DiagnosticParser

            core = None
            if self.track_unsat_core:
                core = self._extract_unsat_core()

            diagnostic = Z3DiagnosticParser.parse_unsat(
                constraints=self._assertions,
                unsat_core=core,
            )

            return CheckResult(
                status="unsat",
                satisfiable=False,
                unsat_core=core,
                diagnostic=diagnostic,
            )
        else:
            from logos.diagnostics import Diagnostic, ErrorType

            reason = self._solver.reason_unknown()
            suggestions = ["Try simplifying constraints", "Increase solver timeout"]
            error_type = ErrorType.UNKNOWN
            if "timeout" in reason.lower():
                error_type = ErrorType.TIMEOUT

            return CheckResult(
                status="unknown",
                satisfiable=None,
                reason=reason,
                diagnostic=Diagnostic(
                    error_type=error_type,
                    message=f"Solver returned unknown: {reason}",
                    suggestions=suggestions,
                ),
            )

    def push(self) -> None:
        """Create a new scope for backtracking.
        
        All assertions made after push() can be undone with pop().
        
        Example
        -------
        >>> session.assert_constraint("x > 0")
        >>> session.push()
        >>> session.assert_constraint("x < 0")  # Contradicts!
        >>> session.check()  # unsat
        >>> session.pop()    # Remove "x < 0"
        >>> session.check()  # sat again
        """
        self._solver.push()
        self._scope_depth += 1

    def pop(self, n: int = 1) -> None:
        """Pop n scopes, removing all assertions made in those scopes.
        
        Parameters
        ----------
        n : int
            Number of scopes to pop. Default is 1.
        
        Raises
        ------
        ValueError
            If trying to pop more scopes than pushed.
        """
        if n > self._scope_depth:
            raise ValueError(
                f"Cannot pop {n} scopes; only {self._scope_depth} active"
            )
        self._solver.pop(n)
        self._scope_depth -= n

    def reset(self) -> None:
        """Reset the session, clearing all state."""
        self._solver.reset()
        self._variables.clear()
        self._assertions.clear()
        self._assertion_names.clear()
        self._scope_depth = 0

        # Reapply settings
        self._solver.set("timeout", self.timeout_ms)
        if self.track_unsat_core:
            self._solver.set("unsat_core", True)

    @property
    def num_assertions(self) -> int:
        """Number of assertions in the solver."""
        return len(self._assertions)

    @property
    def scope_depth(self) -> int:
        """Current scope depth (number of active push() calls)."""
        return self._scope_depth

    @property
    def variables(self) -> list[str]:
        """List of declared variable names."""
        return list(self._variables.keys())

    def _parse_constraint(self, constraint: str) -> z3.BoolRef:
        """Parse a constraint string into a Z3 expression.

        Uses a restricted Python AST translator with explicit allow-listing.
        """
        try:
            expr_str = self._normalize_constraint_syntax(constraint)
            parsed = ast.parse(expr_str, mode="eval")
            result = self._ast_to_z3(parsed.body)
            if isinstance(result, bool):
                result = z3.BoolVal(result)
            if not isinstance(result, z3.BoolRef):
                raise ConstraintError(
                    f"Constraint '{constraint}' did not evaluate to a boolean expression"
                )
            return result
        except ConstraintError:
            raise
        except Exception as e:
            raise ConstraintError(f"Failed to parse constraint '{constraint}': {e}")

    def _normalize_constraint_syntax(self, constraint: str) -> str:
        """Normalize user-friendly operators into parseable Python syntax."""
        expr_str = constraint
        expr_str = expr_str.replace("&&", " and ")
        expr_str = expr_str.replace("||", " or ")
        expr_str = re.sub(r"(?<![=!<>])!(?!=)", " not ", expr_str)
        expr_str = self._rewrite_implication(expr_str)
        expr_str = re.sub(r'(?<![<>=!])=(?![=])', '==', expr_str)
        return expr_str

    def _rewrite_implication(self, expr: str) -> str:
        """Rewrite `a -> b` / `a => b` to `Implies(a, b)` (right-associative)."""
        index = self._find_top_level_implication(expr)
        if index is None:
            return expr

        op_len = 2
        left = expr[:index].strip()
        right = expr[index + op_len :].strip()

        if not left or not right:
            raise ConstraintError("Incomplete implication expression")

        return f"Implies({self._rewrite_implication(left)}, {self._rewrite_implication(right)})"

    def _find_top_level_implication(self, expr: str) -> Optional[int]:
        """Find right-most top-level implication operator (`->` or `=>`)."""
        depth = 0
        i = len(expr) - 2
        while i >= 0:
            ch = expr[i]
            if ch == ")":
                depth += 1
                i -= 1
                continue
            if ch == "(":
                depth -= 1
                i -= 1
                continue

            if depth == 0:
                token = expr[i : i + 2]
                if token in {"->", "=>"}:
                    return i
            i -= 1
        return None

    def _ast_to_z3(self, node: ast.AST) -> Any:
        """Translate a restricted Python AST expression into a Z3 expression."""
        if isinstance(node, ast.Name):
            if node.id in self._variables:
                return self._variables[node.id]
            if node.id == "True":
                return z3.BoolVal(True)
            if node.id == "False":
                return z3.BoolVal(False)
            raise ConstraintError(f"Undeclared variable '{node.id}'")

        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return z3.BoolVal(node.value)
            if isinstance(node.value, int):
                return z3.IntVal(node.value)
            if isinstance(node.value, float):
                return z3.RealVal(str(node.value))
            raise ConstraintError(f"Unsupported constant type: {type(node.value).__name__}")

        if isinstance(node, ast.UnaryOp):
            operand = self._ast_to_z3(node.operand)
            if isinstance(node.op, ast.Not):
                return z3.Not(operand)
            if isinstance(node.op, ast.USub):
                return -operand
            raise ConstraintError(f"Unsupported unary operator: {type(node.op).__name__}")

        if isinstance(node, ast.BoolOp):
            values = [self._ast_to_z3(v) for v in node.values]
            if isinstance(node.op, ast.And):
                return z3.And(*values)
            if isinstance(node.op, ast.Or):
                return z3.Or(*values)
            raise ConstraintError(f"Unsupported boolean operator: {type(node.op).__name__}")

        if isinstance(node, ast.BinOp):
            left = self._ast_to_z3(node.left)
            right = self._ast_to_z3(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Mod):
                return left % right
            raise ConstraintError(f"Unsupported binary operator: {type(node.op).__name__}")

        if isinstance(node, ast.Compare):
            left = self._ast_to_z3(node.left)
            comparisons: list[z3.BoolRef] = []

            for op, right_node in zip(node.ops, node.comparators):
                right = self._ast_to_z3(right_node)
                if isinstance(op, ast.Eq):
                    comparisons.append(left == right)
                elif isinstance(op, ast.NotEq):
                    comparisons.append(left != right)
                elif isinstance(op, ast.Gt):
                    comparisons.append(left > right)
                elif isinstance(op, ast.GtE):
                    comparisons.append(left >= right)
                elif isinstance(op, ast.Lt):
                    comparisons.append(left < right)
                elif isinstance(op, ast.LtE):
                    comparisons.append(left <= right)
                else:
                    raise ConstraintError(f"Unsupported comparison operator: {type(op).__name__}")
                left = right

            if len(comparisons) == 1:
                return comparisons[0]
            return z3.And(*comparisons)

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ConstraintError("Only direct function calls are supported")

            fn_name = node.func.id
            args = [self._ast_to_z3(arg) for arg in node.args]

            if fn_name == "And":
                return z3.And(*args)
            if fn_name == "Or":
                return z3.Or(*args)
            if fn_name == "Not":
                if len(args) != 1:
                    raise ConstraintError("Not() expects exactly one argument")
                return z3.Not(args[0])
            if fn_name == "Implies":
                if len(args) != 2:
                    raise ConstraintError("Implies() expects exactly two arguments")
                return z3.Implies(args[0], args[1])
            if fn_name == "If":
                if len(args) != 3:
                    raise ConstraintError("If() expects exactly three arguments")
                return z3.If(args[0], args[1], args[2])
            if fn_name == "Abs":
                if len(args) != 1:
                    raise ConstraintError("Abs() expects exactly one argument")
                x = args[0]
                return z3.If(x >= 0, x, -x)

            raise ConstraintError(f"Unsupported function: {fn_name}")

        if isinstance(node, ast.IfExp):
            cond = self._ast_to_z3(node.test)
            body = self._ast_to_z3(node.body)
            orelse = self._ast_to_z3(node.orelse)
            return z3.If(cond, body, orelse)

        raise ConstraintError(f"Unsupported syntax node: {type(node).__name__}")

    def _extract_model(self, model: z3.ModelRef) -> dict[str, Any]:
        """Extract variable values from a Z3 model."""
        result = {}
        for name, var in self._variables.items():
            val = model.evaluate(var, model_completion=True)
            # Convert Z3 values to Python values
            if z3.is_int_value(val):
                as_long = getattr(cast(Any, val), "as_long", None)
                result[name] = as_long() if callable(as_long) else str(val)
            elif z3.is_rational_value(val):
                as_fraction = getattr(cast(Any, val), "as_fraction", None)
                result[name] = float(cast(Any, as_fraction)()) if callable(as_fraction) else str(val)
            elif z3.is_true(val):
                result[name] = True
            elif z3.is_false(val):
                result[name] = False
            else:
                result[name] = str(val)
        return result

    def _extract_unsat_core(self) -> list[str]:
        """Extract named assertions from the unsat core."""
        core = self._solver.unsat_core()
        names = []
        for c in core:
            name = str(c)
            if name.startswith("__track_"):
                names.append(name[8:])  # Remove prefix
            else:
                names.append(name)
        return names
