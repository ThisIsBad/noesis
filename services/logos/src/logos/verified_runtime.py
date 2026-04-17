"""Closed-loop deterministic runtime for verified agent execution."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from logos.action_policy import ActionPolicyEngine
from logos.counterfactual import CounterfactualPlanner, PlanBranch
from logos.execution_bus import ActionBusResult, ActionEnvelope, ToolAdapter, execute_action_envelope
from logos.goal_contract import (
    GoalContract,
    GoalContractResult,
    GoalContractStatus,
    build_branch_context,
    evaluate_goal_contract,
)
from logos.recovery import FailureCategory, FailureContext, RecoveryDecision, choose_recovery
from logos.certificate import ProofCertificate
from logos.uncertainty import (
    EscalationDecision,
    EscalationResult,
    RiskLevel,
    UncertaintyCalibrator,
    UncertaintyPolicy,
)

SCHEMA_VERSION = "1.0"
JSONValue = Any


class RuntimePhase(Enum):
    """Deterministic runtime phases."""

    PLANNING = "planning"
    CONTRACT = "contract"
    UNCERTAINTY = "uncertainty"
    EXECUTION = "execution"
    RECOVERY = "recovery"
    COMPLETED = "completed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class RuntimeEvent:
    """One auditable runtime event."""

    phase: RuntimePhase
    payload: dict[str, JSONValue]

    def to_dict(self) -> dict[str, JSONValue]:
        return {"phase": self.phase.value, "payload": dict(self.payload)}


@dataclass(frozen=True)
class RuntimeTrace:
    """Ordered event log for one runtime request."""

    request_id: str
    events: tuple[RuntimeEvent, ...]

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": SCHEMA_VERSION,
            "request_id": self.request_id,
            "events": [event.to_dict() for event in self.events],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


@dataclass(frozen=True)
class RuntimeRequest:
    """Inputs for one verified runtime iteration."""

    request_id: str
    branch_id: str
    strategy: str
    contract: GoalContract
    action_envelope: ActionEnvelope
    proof_certificate: ProofCertificate
    risk_level: RiskLevel
    policy_action: dict[str, bool] | None = None
    context_overrides: dict[str, bool] | None = None
    max_retries: int = 0
    retry_count: int = 0


@dataclass(frozen=True)
class RuntimeOutcome:
    """Deterministic runtime result."""

    phase: RuntimePhase
    completed: bool
    blocked: bool
    branch: PlanBranch
    contract_result: GoalContractResult | None
    escalation_result: EscalationResult | None
    action_result: ActionBusResult | None
    recovery_decision: RecoveryDecision | None
    trace: RuntimeTrace


class VerifiedAgentRuntime:
    """Compose planning, contracts, uncertainty, execution, and recovery."""

    def __init__(
        self,
        planner: CounterfactualPlanner,
        *,
        policy_engine: ActionPolicyEngine | None = None,
        uncertainty_calibrator: UncertaintyCalibrator | None = None,
        uncertainty_policy: UncertaintyPolicy | None = None,
    ) -> None:
        self._planner = planner
        self._policy_engine = policy_engine
        self._uncertainty_calibrator = uncertainty_calibrator or UncertaintyCalibrator()
        self._uncertainty_policy = uncertainty_policy

    def run(self, request: RuntimeRequest, adapters: Mapping[str, ToolAdapter]) -> RuntimeOutcome:
        """Execute one closed-loop deterministic runtime cycle."""
        events: list[RuntimeEvent] = []
        branch = self._planner.get_branch(request.branch_id)
        events.append(
            RuntimeEvent(
                phase=RuntimePhase.PLANNING,
                payload={
                    "branch_id": branch.branch_id,
                    "status": branch.status,
                    "satisfiable": branch.satisfiable,
                    "trace": list(branch.trace),
                },
            )
        )

        if branch.satisfiable is not True:
            recovery = choose_recovery(
                _plan_failure_context(branch, retry_count=request.retry_count, max_retries=request.max_retries)
            )
            events.append(_recovery_event(recovery))
            return _runtime_outcome(
                request_id=request.request_id,
                phase=RuntimePhase.BLOCKED,
                blocked=True,
                completed=False,
                branch=branch,
                contract_result=None,
                escalation_result=None,
                action_result=None,
                recovery_decision=recovery,
                events=events,
            )

        context = build_branch_context(branch)
        if request.context_overrides:
            context.update(request.context_overrides)

        contract_result = evaluate_goal_contract(
            request.contract,
            strategy=request.strategy,
            context=context,
            policy_engine=self._policy_engine,
            policy_action=request.policy_action,
        )
        events.append(
            RuntimeEvent(
                phase=RuntimePhase.CONTRACT,
                payload={
                    "status": contract_result.status.value,
                    "diagnostic_codes": [diagnostic.code for diagnostic in contract_result.diagnostics],
                    "policy_decision": None
                    if contract_result.policy_decision is None
                    else contract_result.policy_decision.value,
                },
            )
        )

        if contract_result.status in {GoalContractStatus.BLOCKED, GoalContractStatus.ABORTED}:
            recovery = choose_recovery(
                _contract_failure_context(
                    contract_result,
                    retry_count=request.retry_count,
                    max_retries=request.max_retries,
                )
            )
            events.append(_recovery_event(recovery))
            return _runtime_outcome(
                request_id=request.request_id,
                phase=RuntimePhase.BLOCKED,
                blocked=True,
                completed=False,
                branch=branch,
                contract_result=contract_result,
                escalation_result=None,
                action_result=None,
                recovery_decision=recovery,
                events=events,
            )

        confidence_record = self._uncertainty_calibrator.from_certificate(request.proof_certificate)
        escalation_result = self._uncertainty_calibrator.enforce(
            confidence_record,
            request.risk_level,
            policy=self._uncertainty_policy,
        )
        events.append(
            RuntimeEvent(
                phase=RuntimePhase.UNCERTAINTY,
                payload={
                    "decision": escalation_result.decision.value,
                    "reason": escalation_result.reason,
                    "risk_level": request.risk_level.value,
                    "confidence_level": confidence_record.level.value,
                    "certificate_ref": confidence_record.linked_certificate_ref,
                },
            )
        )

        if escalation_result.decision is not EscalationDecision.PROCEED:
            recovery = choose_recovery(
                FailureContext(
                    category=FailureCategory.POLICY_BLOCK,
                    source="uncertainty",
                    retry_count=request.retry_count,
                    max_retries=request.max_retries,
                    details={
                        "decision": escalation_result.decision.value,
                        "risk_level": request.risk_level.value,
                        "reason": escalation_result.reason,
                    },
                )
            )
            events.append(_recovery_event(recovery))
            return _runtime_outcome(
                request_id=request.request_id,
                phase=RuntimePhase.BLOCKED,
                blocked=True,
                completed=False,
                branch=branch,
                contract_result=contract_result,
                escalation_result=escalation_result,
                action_result=None,
                recovery_decision=recovery,
                events=events,
            )

        action_result = execute_action_envelope(request.action_envelope, adapters)
        events.append(
            RuntimeEvent(
                phase=RuntimePhase.EXECUTION,
                payload={
                    "status": action_result.status,
                    "accepted": action_result.accepted,
                    "decision": action_result.trace.get("decision"),
                    "diagnostic_codes": [str(item.get("code", "")) for item in action_result.diagnostics],
                },
            )
        )

        if action_result.status != "completed":
            recovery = choose_recovery(
                FailureContext(
                    category=_action_failure_category(action_result),
                    source="execution_bus",
                    retry_count=request.retry_count,
                    max_retries=request.max_retries,
                    details={
                        "status": action_result.status,
                        "diagnostic_codes": [str(item.get("code", "")) for item in action_result.diagnostics],
                    },
                )
            )
            events.append(_recovery_event(recovery))
            return _runtime_outcome(
                request_id=request.request_id,
                phase=RuntimePhase.BLOCKED,
                blocked=True,
                completed=False,
                branch=branch,
                contract_result=contract_result,
                escalation_result=escalation_result,
                action_result=action_result,
                recovery_decision=recovery,
                events=events,
            )

        events.append(
            RuntimeEvent(
                phase=RuntimePhase.COMPLETED,
                payload={
                    "request_id": request.request_id,
                    "branch_id": branch.branch_id,
                    "action_status": action_result.status,
                },
            )
        )
        return _runtime_outcome(
            request_id=request.request_id,
            phase=RuntimePhase.COMPLETED,
            blocked=False,
            completed=True,
            branch=branch,
            contract_result=contract_result,
            escalation_result=escalation_result,
            action_result=action_result,
            recovery_decision=None,
            events=events,
        )

    def replay(
        self,
        request: RuntimeRequest,
        adapters: Mapping[str, ToolAdapter],
        trace: RuntimeTrace,
    ) -> RuntimeOutcome:
        """Re-run a request and require the same deterministic trace."""
        replayed = self.run(request, adapters)
        if replayed.trace.to_dict() != trace.to_dict():
            raise ValueError("Runtime replay diverged from recorded trace")
        return replayed


def _runtime_outcome(
    *,
    request_id: str,
    phase: RuntimePhase,
    blocked: bool,
    completed: bool,
    branch: PlanBranch,
    contract_result: GoalContractResult | None,
    escalation_result: EscalationResult | None,
    action_result: ActionBusResult | None,
    recovery_decision: RecoveryDecision | None,
    events: list[RuntimeEvent],
) -> RuntimeOutcome:
    return RuntimeOutcome(
        phase=phase,
        completed=completed,
        blocked=blocked,
        branch=branch,
        contract_result=contract_result,
        escalation_result=escalation_result,
        action_result=action_result,
        recovery_decision=recovery_decision,
        trace=RuntimeTrace(request_id=request_id, events=tuple(events)),
    )


def _action_failure_category(result: ActionBusResult) -> FailureCategory:
    if result.status == "rejected_preconditions":
        return FailureCategory.PRECONDITION_FAILURE
    if result.status == "rejected_unknown_action":
        return FailureCategory.UNKNOWN_ACTION
    return FailureCategory.POSTCONDITION_FAILURE


def _plan_failure_context(branch: PlanBranch, *, retry_count: int, max_retries: int) -> FailureContext:
    return FailureContext(
        category=FailureCategory.PLAN_INFEASIBLE if branch.satisfiable is False else FailureCategory.PLAN_UNKNOWN,
        source="counterfactual",
        retry_count=retry_count,
        max_retries=max_retries,
        details={"branch_id": branch.branch_id, "status": branch.status},
    )


def _contract_failure_context(
    result: GoalContractResult,
    *,
    retry_count: int,
    max_retries: int,
) -> FailureContext:
    if result.status is GoalContractStatus.ABORTED:
        category = FailureCategory.CONTRACT_ABORT
    else:
        category = FailureCategory.CONTRACT_BLOCK
    return FailureContext(
        category=category,
        source="goal_contract",
        retry_count=retry_count,
        max_retries=max_retries,
        details={
            "status": result.status.value,
            "diagnostic_codes": [diagnostic.code for diagnostic in result.diagnostics],
        },
    )


def _recovery_event(decision: RecoveryDecision) -> RuntimeEvent:
    return RuntimeEvent(
        phase=RuntimePhase.RECOVERY,
        payload={
            "selected_protocol": decision.selected_protocol.value,
            "allowed_protocols": [protocol.value for protocol in decision.allowed_protocols],
            "guard_triggered": decision.guard_triggered,
            "rationale": decision.rationale,
        },
    )
