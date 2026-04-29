"""Goal contracts and deterministic strategy verification."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from logos.action_policy import ActionPolicyEngine, PolicyDecision
from logos.counterfactual import PlanBranch
from logos.z3_session import CheckResult
from logos.schema_utils import (
    load_json_object,
    require_list_of_str,
    require_str,
)

SCHEMA_VERSION = "1.0"


class GoalContractStatus(Enum):
    """Evaluation status for one goal contract check."""

    BLOCKED = "blocked"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABORTED = "aborted"


@dataclass(frozen=True)
class GoalContractDiagnostic:
    """Structured diagnostics for contract violations or drift."""

    code: str
    message: str


@dataclass(frozen=True)
class GoalContract:
    """Machine-checkable goal contract."""

    contract_id: str
    preconditions: tuple[str, ...] = ()
    invariants: tuple[str, ...] = ()
    completion_criteria: tuple[str, ...] = ()
    abort_criteria: tuple[str, ...] = ()
    permitted_strategies: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        """Serialize contract payload."""
        return {
            "schema_version": self.schema_version,
            "contract_id": self.contract_id,
            "preconditions": list(self.preconditions),
            "invariants": list(self.invariants),
            "completion_criteria": list(self.completion_criteria),
            "abort_criteria": list(self.abort_criteria),
            "permitted_strategies": list(self.permitted_strategies),
        }

    def to_json(self) -> str:
        """Serialize contract to JSON."""
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "GoalContract":
        """Deserialize contract from dictionary."""
        schema_version = require_str(
            payload.get("schema_version"),
            "Goal contract field 'schema_version' must be a string",
        )
        if schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported goal contract schema version '{schema_version}'")

        contract_id = require_str(
            payload.get("contract_id"),
            "Goal contract field 'contract_id' must be a string",
        )
        preconditions = tuple(
            require_list_of_str(
                payload.get("preconditions", []),
                "Goal contract field 'preconditions' must be list[str]",
            )
        )
        invariants = tuple(
            require_list_of_str(
                payload.get("invariants", []),
                "Goal contract field 'invariants' must be list[str]",
            )
        )
        completion_criteria = tuple(
            require_list_of_str(
                payload.get("completion_criteria", []),
                "Goal contract field 'completion_criteria' must be list[str]",
            )
        )
        abort_criteria = tuple(
            require_list_of_str(
                payload.get("abort_criteria", []),
                "Goal contract field 'abort_criteria' must be list[str]",
            )
        )
        permitted_strategies = tuple(
            require_list_of_str(
                payload.get("permitted_strategies", []),
                "Goal contract field 'permitted_strategies' must be list[str]",
            )
        )

        return cls(
            contract_id=contract_id,
            preconditions=preconditions,
            invariants=invariants,
            completion_criteria=completion_criteria,
            abort_criteria=abort_criteria,
            permitted_strategies=permitted_strategies,
            schema_version=schema_version,
        )

    @classmethod
    def from_json(cls, raw_json: str) -> "GoalContract":
        """Deserialize contract from JSON."""
        payload = load_json_object(
            raw_json,
            invalid_error="Invalid goal contract JSON",
            object_error="Goal contract JSON must be an object",
        )
        return cls.from_dict(payload)


@dataclass(frozen=True)
class GoalContractResult:
    """Deterministic evaluation output for one contract check."""

    status: GoalContractStatus
    diagnostics: tuple[GoalContractDiagnostic, ...]
    policy_decision: PolicyDecision | None = None
    unsat_core: tuple[str, ...] = ()
    solver_status: str | None = None
    reason: str | None = None


def build_branch_context(branch: PlanBranch) -> dict[str, bool]:
    """Build a deterministic boolean context from a planner branch."""
    return {
        "sat": branch.satisfiable is True,
        "unsat": branch.satisfiable is False,
        "unknown": branch.satisfiable is None,
        "has_scores": len(branch.scores) > 0,
    }


def evaluate_goal_contract(
    contract: GoalContract,
    *,
    strategy: str,
    context: dict[str, bool],
    policy_engine: ActionPolicyEngine | None = None,
    policy_action: dict[str, bool] | None = None,
) -> GoalContractResult:
    """Evaluate a goal contract deterministically against a context."""
    diagnostics: list[GoalContractDiagnostic] = []
    policy_decision: PolicyDecision | None = None

    if contract.permitted_strategies and strategy not in contract.permitted_strategies:
        diagnostics.append(
            GoalContractDiagnostic(
                code="strategy_not_permitted",
                message=f"Strategy '{strategy}' is not permitted by contract",
            )
        )
        return GoalContractResult(status=GoalContractStatus.BLOCKED, diagnostics=tuple(diagnostics))

    if not _all_clauses_hold(contract.preconditions, context):
        diagnostics.append(
            GoalContractDiagnostic(
                code="precondition_failed",
                message="One or more preconditions are not satisfied",
            )
        )
        return GoalContractResult(status=GoalContractStatus.BLOCKED, diagnostics=tuple(diagnostics))

    if _any_clause_holds(contract.abort_criteria, context):
        diagnostics.append(
            GoalContractDiagnostic(
                code="abort_criteria_triggered",
                message="Abort criteria triggered",
            )
        )
        return GoalContractResult(status=GoalContractStatus.ABORTED, diagnostics=tuple(diagnostics))

    if not _all_clauses_hold(contract.invariants, context):
        diagnostics.append(
            GoalContractDiagnostic(
                code="invariant_failed",
                message="Invariant drift detected",
            )
        )
        return GoalContractResult(status=GoalContractStatus.ABORTED, diagnostics=tuple(diagnostics))

    if policy_engine is not None:
        action_context = policy_action or context
        policy_result = policy_engine.evaluate(action_context)
        policy_decision = policy_result.decision
        if policy_result.decision is PolicyDecision.BLOCK:
            diagnostics.append(
                GoalContractDiagnostic(
                    code="policy_block",
                    message="Action policy blocked the contract execution",
                )
            )
            return GoalContractResult(
                status=GoalContractStatus.BLOCKED,
                diagnostics=tuple(diagnostics),
                policy_decision=policy_decision,
            )

    if contract.completion_criteria and _all_clauses_hold(contract.completion_criteria, context):
        return GoalContractResult(
            status=GoalContractStatus.COMPLETED,
            diagnostics=tuple(diagnostics),
            policy_decision=policy_decision,
        )

    return GoalContractResult(
        status=GoalContractStatus.ACTIVE,
        diagnostics=tuple(diagnostics),
        policy_decision=policy_decision,
    )


def _all_clauses_hold(clauses: tuple[str, ...], context: dict[str, bool]) -> bool:
    return all(_evaluate_clause(clause, context) for clause in clauses)


def _any_clause_holds(clauses: tuple[str, ...], context: dict[str, bool]) -> bool:
    return any(_evaluate_clause(clause, context) for clause in clauses)


def _evaluate_clause(clause: str, context: dict[str, bool]) -> bool:
    if clause.startswith("!"):
        key = clause[1:]
        return not context.get(key, False)
    return context.get(clause, False)


def verify_contract_preconditions_z3(
    contract: GoalContract,
    state_constraints: list[str],
    variables: dict[str, str] | None = None,
    timeout_ms: int = 30000,
) -> GoalContractResult:
    """Verify goal contract preconditions against Z3 state constraints.

    Each precondition and state constraint is parsed as a Z3 formula.
    The check asks: given the state constraints, are all preconditions
    necessarily satisfied?

    This uses two Z3 queries over the full precondition conjunction:
    first, check whether the state and preconditions are jointly
    satisfiable; second, use proof-by-refutation by asserting the state
    and the negation of the full precondition conjunction. If that second
    query is UNSAT, the preconditions hold.

    Parameters
    ----------
    contract : GoalContract
        The contract whose preconditions to verify.
    state_constraints : list[str]
        Z3-parseable constraints describing the current state.
    variables : dict[str, str] | None
        Variable declarations as ``{name: sort}``.
    timeout_ms : int
        Z3 solver timeout.

    Returns
    -------
    GoalContractResult
        ACTIVE if all preconditions hold, BLOCKED if any fails or Z3
        returns ``unknown``.
    """
    from logos.z3_session import Z3Session

    diagnostics: list[GoalContractDiagnostic] = []
    if not contract.preconditions:
        return GoalContractResult(
            status=GoalContractStatus.ACTIVE,
            diagnostics=(),
            solver_status="sat",
        )

    consistency_session = Z3Session(timeout_ms=timeout_ms)
    _declare_contract_variables(
        consistency_session,
        variables=variables,
        statements=state_constraints + list(contract.preconditions),
    )
    for constraint in state_constraints:
        consistency_session.assert_constraint(constraint)
    for precondition in contract.preconditions:
        consistency_session.assert_constraint(precondition)

    consistency_result = consistency_session.check()
    if consistency_result.satisfiable is False:
        unsat_core = _minimize_unsat_contract_clauses(
            state_constraints=state_constraints,
            preconditions=contract.preconditions,
            variables=variables,
            timeout_ms=timeout_ms,
        )
        diagnostics.append(
            GoalContractDiagnostic(
                code="z3_preconditions_unsat",
                message="State constraints and contract preconditions are jointly unsatisfiable",
            )
        )
        return GoalContractResult(
            status=GoalContractStatus.BLOCKED,
            diagnostics=tuple(diagnostics),
            unsat_core=unsat_core,
            solver_status=consistency_result.status,
            reason=consistency_result.reason,
        )
    if consistency_result.satisfiable is None:
        diagnostics.append(
            GoalContractDiagnostic(
                code="z3_precondition_unknown",
                message="Z3 could not determine whether the contract preconditions are satisfiable",
            )
        )
        return GoalContractResult(
            status=GoalContractStatus.BLOCKED,
            diagnostics=tuple(diagnostics),
            solver_status=consistency_result.status,
            reason=consistency_result.reason,
        )

    entailment_session = Z3Session(timeout_ms=timeout_ms)
    _declare_contract_variables(
        entailment_session,
        variables=variables,
        statements=state_constraints + list(contract.preconditions),
    )
    for constraint in state_constraints:
        entailment_session.assert_constraint(constraint)
    entailment_session.assert_constraint(f"not ({_combine_clauses_with_and(contract.preconditions)})")

    entailment_result = entailment_session.check()
    if entailment_result.satisfiable is True:
        diagnostics.append(
            GoalContractDiagnostic(
                code="z3_precondition_not_entailed",
                message="One or more preconditions are not entailed by state",
            )
        )
        return GoalContractResult(
            status=GoalContractStatus.BLOCKED,
            diagnostics=tuple(diagnostics),
            solver_status=entailment_result.status,
            reason=entailment_result.reason,
        )
    if entailment_result.satisfiable is None:
        diagnostics.append(
            GoalContractDiagnostic(
                code="z3_precondition_unknown",
                message="Z3 could not determine whether the contract preconditions are entailed by state",
            )
        )
        return GoalContractResult(
            status=GoalContractStatus.BLOCKED,
            diagnostics=tuple(diagnostics),
            solver_status=entailment_result.status,
            reason=entailment_result.reason,
        )

    return GoalContractResult(
        status=GoalContractStatus.ACTIVE,
        diagnostics=(),
        solver_status=entailment_result.status,
    )


def _declare_contract_variables(
    session: object,
    *,
    variables: dict[str, str] | None,
    statements: list[str],
) -> None:
    declare = getattr(session, "declare")
    if variables is not None:
        for var_name, sort in variables.items():
            declare(var_name, sort)
        return
    _auto_declare_contract_variables(session, statements)


def _combine_clauses_with_and(clauses: tuple[str, ...]) -> str:
    return " and ".join(f"({clause})" for clause in clauses)


def _minimize_unsat_contract_clauses(
    *,
    state_constraints: list[str],
    preconditions: tuple[str, ...],
    variables: dict[str, str] | None,
    timeout_ms: int,
) -> tuple[str, ...]:
    clauses = list(state_constraints) + list(preconditions)
    index = 0

    while index < len(clauses):
        candidate = clauses[:index] + clauses[index + 1 :]
        if not candidate:
            index += 1
            continue
        result = _check_contract_clause_set(candidate, variables=variables, timeout_ms=timeout_ms)
        if result.satisfiable is False:
            clauses = candidate
            continue
        index += 1

    return tuple(clauses)


def _check_contract_clause_set(
    clauses: list[str],
    *,
    variables: dict[str, str] | None,
    timeout_ms: int,
) -> CheckResult:
    from logos.z3_session import Z3Session

    session = Z3Session(timeout_ms=timeout_ms)
    _declare_contract_variables(session, variables=variables, statements=clauses)
    for clause in clauses:
        session.assert_constraint(clause)
    return session.check()


def _auto_declare_contract_variables(session: object, statements: list[str]) -> None:
    """Best-effort auto-declare single-letter variables as Int."""
    import re

    declare = getattr(session, "declare")
    declared: set[str] = set()
    for statement in statements:
        for match in re.finditer(r"\b([a-z])\b", statement):
            name = match.group(1)
            if name not in declared:
                declare(name, "Int")
                declared.add(name)
