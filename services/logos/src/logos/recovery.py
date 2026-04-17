"""Deterministic recovery protocols for failed proof and planning paths."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from logos.action_policy import PolicyDecision
from logos.execution_bus import ActionBusResult
from logos.goal_contract import GoalContractResult, GoalContractStatus
from logos.orchestrator import Claim, ClaimStatus
from logos.counterfactual import PlanBranch

SCHEMA_VERSION = "1.0"
JSONValue = Any


class FailureCategory(Enum):
    """Normalized failure taxonomy across LogicBrain modules."""

    PRECONDITION_FAILURE = "precondition_failure"
    POSTCONDITION_FAILURE = "postcondition_failure"
    UNKNOWN_ACTION = "unknown_action"
    POLICY_BLOCK = "policy_block"
    CONTRACT_BLOCK = "contract_block"
    CONTRACT_ABORT = "contract_abort"
    PROOF_FAILURE = "proof_failure"
    COMPOSITION_FAILURE = "composition_failure"
    PLAN_INFEASIBLE = "plan_infeasible"
    PLAN_UNKNOWN = "plan_unknown"


class RecoveryProtocol(Enum):
    """Deterministic next-best actions after a failure."""

    RETRY = "retry"
    ROLLBACK = "rollback"
    REPLAN = "replan"
    ESCALATE = "escalate"
    DEFER = "defer"


@dataclass(frozen=True)
class FailureContext:
    """Auditable recovery input."""

    category: FailureCategory
    source: str
    retry_count: int = 0
    max_retries: int = 0
    details: Mapping[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": SCHEMA_VERSION,
            "category": self.category.value,
            "source": self.source,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class RecoveryCertificate:
    """Deterministic evidence that a chosen recovery protocol was compliant."""

    context: FailureContext
    selected_protocol: RecoveryProtocol
    allowed_protocols: tuple[RecoveryProtocol, ...]
    compliant: bool
    rationale: str
    guard_triggered: bool
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.schema_version,
            "context": self.context.to_dict(),
            "selected_protocol": self.selected_protocol.value,
            "allowed_protocols": [protocol.value for protocol in self.allowed_protocols],
            "compliant": self.compliant,
            "rationale": self.rationale,
            "guard_triggered": self.guard_triggered,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "RecoveryCertificate":
        schema_version = payload.get("schema_version")
        if schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported recovery certificate schema version '{schema_version}'")
        context_payload = payload.get("context")
        if not isinstance(context_payload, dict):
            raise ValueError("Recovery certificate field 'context' must be an object")
        context = failure_context_from_dict({str(key): value for key, value in context_payload.items()})
        selected = _protocol_from_value(payload.get("selected_protocol"), "selected_protocol")
        allowed_raw = payload.get("allowed_protocols")
        if not isinstance(allowed_raw, list):
            raise ValueError("Recovery certificate field 'allowed_protocols' must be a list")
        allowed = tuple(_protocol_from_value(item, "allowed_protocols entry") for item in allowed_raw)
        compliant = payload.get("compliant")
        rationale = payload.get("rationale")
        guard_triggered = payload.get("guard_triggered")
        if not isinstance(compliant, bool):
            raise ValueError("Recovery certificate field 'compliant' must be a boolean")
        if not isinstance(rationale, str) or not rationale:
            raise ValueError("Recovery certificate field 'rationale' must be a non-empty string")
        if not isinstance(guard_triggered, bool):
            raise ValueError("Recovery certificate field 'guard_triggered' must be a boolean")
        return cls(
            context=context,
            selected_protocol=selected,
            allowed_protocols=allowed,
            compliant=compliant,
            rationale=rationale,
            guard_triggered=guard_triggered,
            schema_version=SCHEMA_VERSION,
        )

    @classmethod
    def from_json(cls, raw_json: str) -> "RecoveryCertificate":
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid recovery certificate JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("Recovery certificate JSON must be an object")
        return cls.from_dict({str(key): value for key, value in payload.items()})


@dataclass(frozen=True)
class RecoveryDecision:
    """Auditable deterministic recovery choice."""

    allowed_protocols: tuple[RecoveryProtocol, ...]
    selected_protocol: RecoveryProtocol
    rationale: str
    trace: dict[str, JSONValue]
    guard_triggered: bool
    certificate: RecoveryCertificate


DEFAULT_PROTOCOL_GRAPH: dict[FailureCategory, tuple[RecoveryProtocol, ...]] = {
    FailureCategory.PRECONDITION_FAILURE: (
        RecoveryProtocol.RETRY,
        RecoveryProtocol.ESCALATE,
        RecoveryProtocol.DEFER,
    ),
    FailureCategory.POSTCONDITION_FAILURE: (
        RecoveryProtocol.ROLLBACK,
        RecoveryProtocol.REPLAN,
        RecoveryProtocol.ESCALATE,
    ),
    FailureCategory.UNKNOWN_ACTION: (
        RecoveryProtocol.REPLAN,
        RecoveryProtocol.ESCALATE,
        RecoveryProtocol.DEFER,
    ),
    FailureCategory.POLICY_BLOCK: (RecoveryProtocol.ESCALATE, RecoveryProtocol.DEFER),
    FailureCategory.CONTRACT_BLOCK: (
        RecoveryProtocol.REPLAN,
        RecoveryProtocol.ESCALATE,
        RecoveryProtocol.DEFER,
    ),
    FailureCategory.CONTRACT_ABORT: (RecoveryProtocol.ROLLBACK, RecoveryProtocol.ESCALATE, RecoveryProtocol.DEFER),
    FailureCategory.PROOF_FAILURE: (RecoveryProtocol.RETRY, RecoveryProtocol.REPLAN, RecoveryProtocol.ESCALATE),
    FailureCategory.COMPOSITION_FAILURE: (RecoveryProtocol.REPLAN, RecoveryProtocol.ESCALATE, RecoveryProtocol.DEFER),
    FailureCategory.PLAN_INFEASIBLE: (RecoveryProtocol.REPLAN, RecoveryProtocol.ESCALATE, RecoveryProtocol.DEFER),
    FailureCategory.PLAN_UNKNOWN: (RecoveryProtocol.RETRY, RecoveryProtocol.ESCALATE, RecoveryProtocol.DEFER),
}


def failure_context_from_dict(payload: dict[str, JSONValue]) -> FailureContext:
    """Deserialize a failure context."""
    schema_version = payload.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported failure context schema version '{schema_version}'")
    category = _category_from_value(payload.get("category"), "category")
    source = payload.get("source")
    retry_count = payload.get("retry_count", 0)
    max_retries = payload.get("max_retries", 0)
    details = payload.get("details", {})
    if not isinstance(source, str) or not source:
        raise ValueError("Failure context field 'source' must be a non-empty string")
    if not isinstance(retry_count, int) or retry_count < 0:
        raise ValueError("Failure context field 'retry_count' must be a non-negative integer")
    if not isinstance(max_retries, int) or max_retries < 0:
        raise ValueError("Failure context field 'max_retries' must be a non-negative integer")
    if not isinstance(details, dict):
        raise ValueError("Failure context field 'details' must be an object")
    return FailureContext(
        category=category,
        source=source,
        retry_count=retry_count,
        max_retries=max_retries,
        details={str(key): value for key, value in details.items()},
    )


def choose_recovery(
    context: FailureContext,
    *,
    protocol_graph: Mapping[FailureCategory, tuple[RecoveryProtocol, ...]] | None = None,
) -> RecoveryDecision:
    """Choose the deterministic next-best protocol for a failure context."""
    effective_graph = protocol_graph or DEFAULT_PROTOCOL_GRAPH
    allowed = tuple(effective_graph.get(context.category, (RecoveryProtocol.ESCALATE, RecoveryProtocol.DEFER)))
    guard_triggered = False
    if context.retry_count >= context.max_retries and RecoveryProtocol.RETRY in allowed:
        allowed = tuple(protocol for protocol in allowed if protocol is not RecoveryProtocol.RETRY)
        guard_triggered = True
    if not allowed:
        allowed = (RecoveryProtocol.ESCALATE,)
        guard_triggered = True

    selected = allowed[0]
    rationale = _build_rationale(context, selected, guard_triggered)
    trace = {
        "category": context.category.value,
        "source": context.source,
        "retry_count": context.retry_count,
        "max_retries": context.max_retries,
        "allowed_protocols": [protocol.value for protocol in allowed],
        "selected_protocol": selected.value,
        "guard_triggered": guard_triggered,
        "details": dict(context.details),
    }
    certificate = RecoveryCertificate(
        context=context,
        selected_protocol=selected,
        allowed_protocols=allowed,
        compliant=selected in allowed,
        rationale=rationale,
        guard_triggered=guard_triggered,
    )
    return RecoveryDecision(
        allowed_protocols=allowed,
        selected_protocol=selected,
        rationale=rationale,
        trace=trace,
        guard_triggered=guard_triggered,
        certificate=certificate,
    )


def verify_recovery_certificate(certificate: RecoveryCertificate) -> bool:
    """Verify internal consistency of a recovery certificate."""
    expected = choose_recovery(certificate.context)
    return (
        certificate.selected_protocol == expected.selected_protocol
        and certificate.allowed_protocols == expected.allowed_protocols
        and certificate.compliant is True
        and certificate.guard_triggered == expected.guard_triggered
        and certificate.rationale == expected.rationale
    )


def classify_action_bus_failure(
    result: ActionBusResult,
    *,
    retry_count: int = 0,
    max_retries: int = 0,
) -> FailureContext:
    """Normalize action-bus failures into the shared taxonomy."""
    status = result.status
    if status == "rejected_preconditions":
        category = FailureCategory.PRECONDITION_FAILURE
    elif status == "postcondition_mismatch":
        category = FailureCategory.POSTCONDITION_FAILURE
    elif status == "rejected_unknown_action":
        category = FailureCategory.UNKNOWN_ACTION
    else:
        category = FailureCategory.POSTCONDITION_FAILURE

    details = {
        "status": result.status,
        "diagnostic_codes": [str(item.get("code", "")) for item in result.diagnostics],
        "accepted": result.accepted,
    }
    return FailureContext(
        category=category,
        source="execution_bus",
        retry_count=retry_count,
        max_retries=max_retries,
        details=details,
    )


def classify_claim_failure(
    claim: Claim,
    *,
    retry_count: int = 0,
    max_retries: int = 0,
) -> FailureContext:
    """Normalize orchestrator claim failures into the shared taxonomy."""
    if claim.status is not ClaimStatus.FAILED:
        raise ValueError("Claim must be in FAILED state to classify recovery")

    reason = claim.failure_reason.lower()
    if "composition" in reason:
        category = FailureCategory.COMPOSITION_FAILURE
    else:
        category = FailureCategory.PROOF_FAILURE

    return FailureContext(
        category=category,
        source="orchestrator",
        retry_count=retry_count,
        max_retries=max_retries,
        details={"claim_id": claim.claim_id, "failure_reason": claim.failure_reason},
    )


def classify_plan_failure(
    branch: PlanBranch,
    *,
    retry_count: int = 0,
    max_retries: int = 0,
) -> FailureContext:
    """Normalize planner branch failures into the shared taxonomy."""
    if branch.satisfiable is False:
        category = FailureCategory.PLAN_INFEASIBLE
    elif branch.satisfiable is None:
        category = FailureCategory.PLAN_UNKNOWN
    else:
        raise ValueError("Plan branch is feasible and does not require recovery classification")

    return FailureContext(
        category=category,
        source="counterfactual",
        retry_count=retry_count,
        max_retries=max_retries,
        details={"branch_id": branch.branch_id, "status": branch.status},
    )


def classify_goal_contract_failure(
    result: GoalContractResult,
    *,
    retry_count: int = 0,
    max_retries: int = 0,
) -> FailureContext:
    """Normalize goal contract failures into the shared taxonomy."""
    if result.policy_decision is PolicyDecision.BLOCK:
        category = FailureCategory.POLICY_BLOCK
    elif result.status is GoalContractStatus.BLOCKED:
        category = FailureCategory.CONTRACT_BLOCK
    elif result.status is GoalContractStatus.ABORTED:
        category = FailureCategory.CONTRACT_ABORT
    else:
        raise ValueError("Goal contract result does not represent a recoverable failure")

    return FailureContext(
        category=category,
        source="goal_contract",
        retry_count=retry_count,
        max_retries=max_retries,
        details={
            "status": result.status.value,
            "policy_decision": None if result.policy_decision is None else result.policy_decision.value,
            "diagnostic_codes": [diagnostic.code for diagnostic in result.diagnostics],
        },
    )


def _build_rationale(
    context: FailureContext,
    selected: RecoveryProtocol,
    guard_triggered: bool,
) -> str:
    if guard_triggered:
        return (
            f"Selected '{selected.value}' for {context.category.value} after retry guard removed unsafe retry "
            f"at {context.retry_count}/{context.max_retries}."
        )
    return f"Selected '{selected.value}' as the first allowed protocol for {context.category.value}."


def _category_from_value(value: object, field_name: str) -> FailureCategory:
    if not isinstance(value, str):
        raise ValueError(f"Recovery field '{field_name}' must be a string")
    try:
        return FailureCategory(value)
    except ValueError as exc:
        raise ValueError(f"Unknown failure category '{value}'") from exc


def _protocol_from_value(value: object, field_name: str) -> RecoveryProtocol:
    if not isinstance(value, str):
        raise ValueError(f"Recovery field '{field_name}' must be a string")
    try:
        return RecoveryProtocol(value)
    except ValueError as exc:
        raise ValueError(f"Unknown recovery protocol '{value}'") from exc
