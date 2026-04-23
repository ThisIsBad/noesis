"""Adapters that convert service-native decision results into ``DecisionTrace``.

These adapters are *duck-typed* — we don't import Logos / Praxis / Telos
at module load time so Theoria remains a zero-dep service. Callers that
already have an ``ActionPolicyResult`` instance in hand (for example the
Logos MCP server) pass it in; we read only public attributes.
"""

from __future__ import annotations

from typing import Any, Iterable, Protocol
from uuid import uuid4

from theoria.models import (
    DecisionTrace,
    Edge,
    EdgeRelation,
    Outcome,
    ReasoningStep,
    StepKind,
    StepStatus,
)


# ---------------------------------------------------------------------------
# Logos ActionPolicyResult → DecisionTrace
# ---------------------------------------------------------------------------

class _PolicyViolation(Protocol):
    policy_name: str
    severity: str
    message: str
    triggered_fields: list[str]
    z3_witness: dict[str, bool] | None


class _PolicyResult(Protocol):
    decision: Any                  # PolicyDecision enum
    violations: list[_PolicyViolation]
    remediation_hints: list[str]
    solver_status: str | None
    reason: str | None


def trace_from_logos_policy(
    result: _PolicyResult,
    *,
    action: dict[str, bool] | None = None,
    question: str = "Is the proposed action allowed under the current policy set?",
    title: str | None = None,
    trace_id: str | None = None,
) -> DecisionTrace:
    """Build a DecisionTrace from a Logos ``ActionPolicyResult``.

    Arguments:
        result: An object with the ``ActionPolicyResult`` shape.
        action: Optional action-under-evaluation — renders each field as an
            observation node so the UI shows *what* was being checked.
        question: Human-readable prompt shown above the graph.
        title: Graph title (defaults to the decision verdict).
        trace_id: Stable id; auto-generated if omitted.
    """
    decision_name = _enum_name(result.decision).lower()
    trace_id = trace_id or f"logos-policy-{uuid4().hex[:12]}"
    title = title or f"Logos policy decision — {decision_name.upper()}"

    steps: list[ReasoningStep] = []
    edges: list[Edge] = []

    root_id = "q"
    steps.append(
        ReasoningStep(
            id=root_id,
            kind=StepKind.QUESTION,
            label=question,
            detail="Deterministic pre-action policy enforcement (Logos).",
            source_ref="services/logos/src/logos/action_policy.py",
        )
    )

    # Observations: one per action field.
    observation_ids: list[str] = []
    for i, (field, value) in enumerate(sorted((action or {}).items())):
        oid = f"fact.{i}"
        observation_ids.append(oid)
        steps.append(
            ReasoningStep(
                id=oid,
                kind=StepKind.OBSERVATION,
                label=f"{field} = {str(value).lower()}",
                status=StepStatus.OK,
            )
        )
        edges.append(Edge(root_id, oid, EdgeRelation.CONSIDERS))

    # Rule violations become RULE_CHECK nodes.
    for i, violation in enumerate(result.violations):
        vid = f"rule.{i}"
        severity = violation.severity
        status = StepStatus.FAILED if severity == "error" else StepStatus.TRIGGERED
        steps.append(
            ReasoningStep(
                id=vid,
                kind=StepKind.RULE_CHECK,
                label=f"Rule: {violation.policy_name}",
                detail=f"{violation.message}  (severity={severity})",
                status=status,
                meta={
                    "severity": severity,
                    "triggered_fields": list(violation.triggered_fields or []),
                    "z3_witness": dict(violation.z3_witness) if violation.z3_witness else None,
                },
            )
        )
        edges.append(Edge(root_id, vid, EdgeRelation.REQUIRES, "rule check"))
        # Link each triggered field to the rule so the DAG shows provenance.
        for field_name in violation.triggered_fields or []:
            for j, (obs_field, _) in enumerate(sorted((action or {}).items())):
                if obs_field == field_name:
                    edges.append(Edge(f"fact.{j}", vid, EdgeRelation.SUPPORTS, field_name))
                    break

    # Conclusion node.
    concl_id = "conclusion"
    concl_status = {
        "allow": StepStatus.OK,
        "review_required": StepStatus.TRIGGERED,
        "block": StepStatus.FAILED,
    }.get(decision_name, StepStatus.INFO)
    steps.append(
        ReasoningStep(
            id=concl_id,
            kind=StepKind.CONCLUSION,
            label=f"Decision: {decision_name.upper()}",
            detail=result.reason or _default_reason(decision_name, len(result.violations)),
            status=concl_status,
            meta={
                "solver_status": result.solver_status,
                "remediation_hints": list(result.remediation_hints or []),
            },
        )
    )
    for i in range(len(result.violations)):
        edges.append(Edge(f"rule.{i}", concl_id, EdgeRelation.IMPLIES))
    if not result.violations:
        edges.append(Edge(root_id, concl_id, EdgeRelation.YIELDS))

    outcome = Outcome(
        verdict=decision_name,
        summary=(
            result.reason
            or f"{len(result.violations)} violation(s); decision={decision_name}"
        ),
        confidence=1.0 if result.solver_status == "sat" else None,
        meta={"solver_status": result.solver_status},
    )

    trace = DecisionTrace(
        id=trace_id,
        title=title,
        question=question,
        source="logos",
        kind="policy",
        root=root_id,
        steps=steps,
        edges=edges,
        outcome=outcome,
        tags=["logos", "policy", decision_name],
    )
    trace.validate()
    return trace


# ---------------------------------------------------------------------------
# Generic tree → DecisionTrace helper (for lightweight external callers)
# ---------------------------------------------------------------------------

def trace_from_tree(
    *,
    trace_id: str,
    title: str,
    question: str,
    source: str,
    kind: str,
    tree: dict[str, Any],
    outcome: Outcome | None = None,
    tags: Iterable[str] = (),
) -> DecisionTrace:
    """Build a ``DecisionTrace`` from a nested dict of the shape::

        {
          "id": "q", "kind": "question", "label": "...",
          "status": "info",
          "children": [ { ... }, ... ]
        }
    """
    steps: list[ReasoningStep] = []
    edges: list[Edge] = []
    _walk_tree(tree, parent_id=None, steps=steps, edges=edges)
    trace = DecisionTrace(
        id=trace_id,
        title=title,
        question=question,
        source=source,
        kind=kind,
        root=steps[0].id,
        steps=steps,
        edges=edges,
        outcome=outcome,
        tags=list(tags),
    )
    trace.validate()
    return trace


def _walk_tree(
    node: dict[str, Any],
    *,
    parent_id: str | None,
    steps: list[ReasoningStep],
    edges: list[Edge],
) -> None:
    step = ReasoningStep(
        id=str(node.get("id") or f"n{len(steps)}"),
        kind=StepKind(node.get("kind", "note")),
        label=str(node.get("label", "")),
        detail=node.get("detail"),
        status=StepStatus(node.get("status", "info")),
        confidence=node.get("confidence"),
        source_ref=node.get("source_ref"),
        meta=dict(node.get("meta") or {}),
    )
    steps.append(step)
    if parent_id is not None:
        relation_val = node.get("relation", "supports")
        edges.append(Edge(parent_id, step.id, EdgeRelation(relation_val), node.get("edge_label")))
    for child in node.get("children", []) or []:
        _walk_tree(child, parent_id=step.id, steps=steps, edges=edges)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _enum_name(value: Any) -> str:
    name = getattr(value, "name", None)
    if isinstance(name, str):
        return name
    return str(value)


def _default_reason(decision: str, n_violations: int) -> str:
    if decision == "allow":
        return "No rules triggered."
    if decision == "review_required":
        return f"{n_violations} warning-level rule(s) triggered — human review needed."
    if decision == "block":
        return f"{n_violations} rule violation(s); at least one at error severity."
    return "Decision produced."
