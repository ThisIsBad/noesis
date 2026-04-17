"""Counterfactual planning with deterministic branch replay."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Mapping

from logos.certificate import (
    ProofCertificate,
    certify_z3_session,
    verify_certificate,
)
from logos.z3_session import Z3Session


@dataclass(frozen=True)
class VariableDecl:
    """Variable declaration in a planning state."""

    name: str
    sort: str
    size: int | None = None


@dataclass(frozen=True)
class PlanState:
    """Immutable state snapshot for one planning branch."""

    declarations: tuple[VariableDecl, ...] = ()
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanBranch:
    """One branch in a counterfactual plan tree."""

    branch_id: str
    parent_id: str | None
    state: PlanState
    status: str
    satisfiable: bool | None
    model: Mapping[str, Any] | None
    certificate: ProofCertificate
    trace: tuple[str, ...] = ()
    scores: Mapping[str, float] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class PlanResult:
    """Snapshot of planner branches."""

    branches: dict[str, PlanBranch]


@dataclass(frozen=True)
class UtilityModel:
    """Explicit utility terms for branch ranking."""

    expected_value: float = 0.0
    execution_cost: float = 0.0
    risk_penalty: float = 0.0
    confidence_weight: float = 1.0

    def total(self) -> float:
        """Return the deterministic utility score before safety filtering."""
        return self.confidence_weight * self.expected_value - self.execution_cost - self.risk_penalty

    def scaled(self, factor: float) -> "UtilityModel":
        """Return an affine scaling of the additive utility terms."""
        return UtilityModel(
            expected_value=self.expected_value * factor,
            execution_cost=self.execution_cost * factor,
            risk_penalty=self.risk_penalty * factor,
            confidence_weight=self.confidence_weight,
        )


@dataclass(frozen=True)
class SafetyBound:
    """Hard admissibility caps that dominate utility optimization."""

    max_execution_cost: float | None = None
    max_risk_penalty: float | None = None
    min_confidence_weight: float | None = None


@dataclass(frozen=True)
class RankedBranch:
    """Explainable ranking record for one branch."""

    branch_id: str
    rank: int | None
    admissible: bool
    utility_model: UtilityModel
    total_score: float | None
    decomposition: Mapping[str, float]
    safety_violations: tuple[str, ...]
    status: str
    satisfiable: bool | None


class CounterfactualPlanner:
    """Deterministic counterfactual planner over Z3Session semantics."""

    def __init__(self, timeout_ms: int = 30000, track_unsat_core: bool = False) -> None:
        self.timeout_ms = timeout_ms
        self.track_unsat_core = track_unsat_core
        self._root_state = PlanState()
        self._branches: dict[str, PlanBranch] = {}

    def declare(self, name: str, sort: str, size: int | None = None) -> None:
        """Add a declaration to the root planning state."""
        if any(decl.name == name for decl in self._root_state.declarations):
            raise ValueError(f"Variable '{name}' already declared in root state")

        declarations = self._root_state.declarations + (VariableDecl(name, sort, size),)
        self._root_state = PlanState(declarations=declarations, constraints=self._root_state.constraints)

    def assert_constraint(self, constraint: str) -> None:
        """Add a root constraint for all future branches."""
        self._root_state = PlanState(
            declarations=self._root_state.declarations,
            constraints=self._root_state.constraints + (constraint,),
        )

    def branch(
        self,
        branch_id: str,
        additional_constraints: list[str] | None = None,
        parent_id: str | None = None,
    ) -> PlanBranch:
        """Create and evaluate a branch from root or an existing branch."""
        if branch_id in self._branches:
            raise ValueError(f"Branch '{branch_id}' already exists")

        parent_state, trace = self._resolve_parent_state(parent_id)
        extra_constraints = tuple(additional_constraints or [])
        new_state = PlanState(
            declarations=parent_state.declarations,
            constraints=parent_state.constraints + extra_constraints,
        )

        result = self._evaluate_state(new_state)
        new_trace = trace + tuple(f"assert {c}" for c in extra_constraints)
        branch = PlanBranch(
            branch_id=branch_id,
            parent_id=parent_id,
            state=new_state,
            status=result.status,
            satisfiable=result.satisfiable,
            model=_frozen_model(result.model),
            certificate=result.certificate,
            trace=new_trace,
            scores=_frozen_scores(),
        )
        self._branches[branch_id] = branch
        return branch

    def replay(self, branch_id: str) -> PlanBranch:
        """Rebuild a branch from snapshot state and re-evaluate deterministically."""
        branch = self.get_branch(branch_id)
        replay_result = self._evaluate_state(branch.state)

        if replay_result.status != branch.status or replay_result.satisfiable != branch.satisfiable:
            raise ValueError("Branch replay diverged from recorded result")

        return PlanBranch(
            branch_id=branch.branch_id,
            parent_id=branch.parent_id,
            state=branch.state,
            status=replay_result.status,
            satisfiable=replay_result.satisfiable,
            model=_frozen_model(replay_result.model),
            certificate=replay_result.certificate,
            trace=branch.trace,
            scores=_frozen_scores(branch.scores),
        )

    def score_branch(self, branch_id: str, scorers: dict[str, Callable[[PlanBranch], float]]) -> PlanBranch:
        """Apply deterministic scoring hooks to a branch."""
        branch = self.get_branch(branch_id)
        new_scores = dict(branch.scores)
        for score_name, scorer in scorers.items():
            new_scores[score_name] = scorer(branch)

        updated = PlanBranch(
            branch_id=branch.branch_id,
            parent_id=branch.parent_id,
            state=branch.state,
            status=branch.status,
            satisfiable=branch.satisfiable,
            model=_frozen_model(branch.model),
            certificate=branch.certificate,
            trace=branch.trace,
            scores=_frozen_scores(new_scores),
        )
        self._branches[branch_id] = updated
        return updated

    def rank_branches(
        self,
        utility_models: Mapping[str, UtilityModel],
        *,
        safety_bounds: SafetyBound | None = None,
    ) -> tuple[RankedBranch, ...]:
        """Rank feasible branches under explicit utility and hard safety caps."""
        ranked_records: list[RankedBranch] = []

        for branch_id in sorted(self._branches):
            branch = self._branches[branch_id]
            utility_model = utility_models.get(branch_id, UtilityModel())
            admissible, safety_violations = _evaluate_safety(branch, utility_model, safety_bounds)
            total_score = utility_model.total() if admissible else None
            ranked_records.append(
                RankedBranch(
                    branch_id=branch_id,
                    rank=None,
                    admissible=admissible,
                    utility_model=utility_model,
                    total_score=total_score,
                    decomposition=_frozen_ranking_terms(utility_model),
                    safety_violations=safety_violations,
                    status=branch.status,
                    satisfiable=branch.satisfiable,
                )
            )

        admissible_records = sorted(
            (record for record in ranked_records if record.admissible),
            key=lambda record: (-_require_score(record.total_score), record.branch_id),
        )
        rank_lookup = {record.branch_id: index for index, record in enumerate(admissible_records, start=1)}

        return tuple(
            RankedBranch(
                branch_id=record.branch_id,
                rank=rank_lookup.get(record.branch_id),
                admissible=record.admissible,
                utility_model=record.utility_model,
                total_score=record.total_score,
                decomposition=record.decomposition,
                safety_violations=record.safety_violations,
                status=record.status,
                satisfiable=record.satisfiable,
            )
            for record in sorted(
                ranked_records,
                key=lambda record: (
                    record.branch_id not in rank_lookup,
                    rank_lookup.get(record.branch_id, 10**9),
                    record.branch_id,
                ),
            )
        )

    def verify_branch_certificate(self, branch_id: str) -> bool:
        """Independent re-check for a branch certificate."""
        branch = self.get_branch(branch_id)
        return verify_certificate(branch.certificate)

    def get_branch(self, branch_id: str) -> PlanBranch:
        """Get an existing branch by id."""
        if branch_id not in self._branches:
            raise ValueError(f"Unknown branch '{branch_id}'")
        return self._branches[branch_id]

    def result(self) -> PlanResult:
        """Return snapshot of all created branches."""
        return PlanResult(branches=dict(self._branches))

    def _resolve_parent_state(self, parent_id: str | None) -> tuple[PlanState, tuple[str, ...]]:
        if parent_id is None:
            return self._root_state, ()

        if parent_id not in self._branches:
            raise ValueError(f"Unknown parent branch '{parent_id}'")

        parent = self._branches[parent_id]
        return parent.state, parent.trace + (f"fork {parent_id}",)

    def _evaluate_state(self, state: PlanState) -> PlanBranch:
        session = Z3Session(timeout_ms=self.timeout_ms, track_unsat_core=self.track_unsat_core)
        for decl in state.declarations:
            session.declare(decl.name, decl.sort, size=decl.size)
        for constraint in state.constraints:
            session.assert_constraint(constraint)

        check_result = session.check()
        certificate = certify_z3_session(session, check_result)

        return PlanBranch(
            branch_id="__eval__",
            parent_id=None,
            state=state,
            status=check_result.status,
            satisfiable=check_result.satisfiable,
            model=_frozen_model(check_result.model),
            certificate=certificate,
            scores=_frozen_scores(),
        )


def _frozen_scores(scores: Mapping[str, float] | None = None) -> Mapping[str, float]:
    return MappingProxyType(dict(scores or {}))


def _frozen_ranking_terms(model: UtilityModel) -> Mapping[str, float]:
    return MappingProxyType(
        {
            "expected_value": model.expected_value,
            "execution_cost": model.execution_cost,
            "risk_penalty": model.risk_penalty,
            "confidence_weight": model.confidence_weight,
            "total_score": model.total(),
        }
    )


def _evaluate_safety(
    branch: PlanBranch,
    utility_model: UtilityModel,
    safety_bounds: SafetyBound | None,
) -> tuple[bool, tuple[str, ...]]:
    violations: list[str] = []

    if branch.satisfiable is not True:
        violations.append("branch_not_feasible")

    if safety_bounds is not None:
        if (
            safety_bounds.max_execution_cost is not None
            and utility_model.execution_cost > safety_bounds.max_execution_cost
        ):
            violations.append("execution_cost_exceeds_cap")
        if (
            safety_bounds.max_risk_penalty is not None
            and utility_model.risk_penalty > safety_bounds.max_risk_penalty
        ):
            violations.append("risk_penalty_exceeds_cap")
        if (
            safety_bounds.min_confidence_weight is not None
            and utility_model.confidence_weight < safety_bounds.min_confidence_weight
        ):
            violations.append("confidence_weight_below_floor")

    return (len(violations) == 0, tuple(violations))


def _require_score(score: float | None) -> float:
    if score is None:
        raise ValueError("Admissible ranking records must have a numeric score")
    return score


def _frozen_model(model: Mapping[str, Any] | None = None) -> Mapping[str, Any] | None:
    if model is None:
        return None
    return MappingProxyType(dict(model))
