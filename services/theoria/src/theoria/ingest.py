"""Adapters that convert service-native decision results into ``DecisionTrace``.

These adapters are *duck-typed* — we don't import Logos / Praxis / Telos
at module load time so Theoria remains a zero-dep service. Callers that
already have an ``ActionPolicyResult`` instance in hand (for example the
Logos MCP server) pass it in; we read only public attributes.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Protocol, Sequence
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
# Praxis plan tree → DecisionTrace
# ---------------------------------------------------------------------------

# Status strings exported by noesis_schemas.StepStatus (see
# services/praxis/src/praxis/core.py). Kept as strings so we don't
# import noesis_schemas here — the adapter remains duck-typed.
_PRAXIS_STATUS_MAP: Mapping[str, StepStatus] = {
    "pending":   StepStatus.PENDING,
    "completed": StepStatus.OK,
    "failed":    StepStatus.FAILED,
    "skipped":   StepStatus.REJECTED,
}


def trace_from_praxis_plan(
    plan_view: Mapping[str, Any],
    *,
    question: str | None = None,
    title: str | None = None,
    trace_id: str | None = None,
) -> DecisionTrace:
    """Build a DecisionTrace from a Praxis plan-tree view.

    ``plan_view`` is a plain dict so Theoria doesn't have to import
    networkx or noesis_schemas::

        {
            "plan_id": "plan-abc",
            "goal": "Migrate users table",
            "nodes": {
                "s1": {"description": "dump data", "status": "completed",
                       "risk_score": 0.1, "score": 0.9, "tool_call": "pg_dump"},
                "s2": {"description": "alter schema", "status": "pending",
                       "risk_score": 0.5, "score": 0.7},
                ...
            },
            # Parent → child edges. Root is the plan_id itself.
            "edges": [("plan-abc", "s1"), ("s1", "s2"), ("s1", "s3_alt")],
            # Optional: the beam-search winner. Steps on this path get
            # highlighted; competing branches render as pruned alternatives.
            "selected_path": ["s1", "s2"],
        }
    """
    plan_id = str(plan_view.get("plan_id") or "plan")
    goal = str(plan_view.get("goal") or "(no goal specified)")
    nodes: Mapping[str, Mapping[str, Any]] = plan_view.get("nodes") or {}
    edges: Sequence[tuple[str, str]] = plan_view.get("edges") or ()
    selected_path: set[str] = set(plan_view.get("selected_path") or [])

    trace_id = trace_id or f"praxis-plan-{plan_id[:12]}"
    title = title or f"Praxis plan — {goal}"
    question = question or f"Plan: {goal}"

    steps: list[ReasoningStep] = [
        ReasoningStep(
            id="q",
            kind=StepKind.QUESTION,
            label=f"Plan: {goal}",
            detail="Hierarchical planning via Tree-of-Thoughts beam search.",
            source_ref="services/praxis/src/praxis/core.py",
        )
    ]

    for step_id, node in nodes.items():
        status_raw = str(node.get("status", "pending")).lower()
        status = _PRAXIS_STATUS_MAP.get(status_raw, StepStatus.INFO)
        on_best_path = step_id in selected_path
        description = str(node.get("description", step_id))

        if status is StepStatus.FAILED:
            kind = StepKind.ALTERNATIVE
        elif on_best_path and status is StepStatus.OK:
            kind = StepKind.INFERENCE
        elif on_best_path:
            kind = StepKind.INFERENCE
        else:
            kind = StepKind.ALTERNATIVE

        tool_call = node.get("tool_call")
        detail_parts: list[str] = []
        if tool_call:
            detail_parts.append(f"tool: {tool_call}")
        if "risk_score" in node:
            detail_parts.append(f"risk: {float(node['risk_score']):.2f}")
        if "score" in node:
            detail_parts.append(f"score: {float(node['score']):.2f}")
        if node.get("outcome"):
            detail_parts.append(f"outcome: {node['outcome']}")

        steps.append(
            ReasoningStep(
                id=step_id,
                kind=kind,
                label=description,
                detail=" · ".join(detail_parts) or None,
                status=(
                    StepStatus.REJECTED
                    if (not on_best_path and selected_path and status is not StepStatus.FAILED)
                    else status
                ),
                confidence=_optional_float(node.get("score")),
                meta={"risk_score": node.get("risk_score"), "tool_call": tool_call},
            )
        )

    trace_edges: list[Edge] = []
    for parent, child in edges:
        # Parent may be the plan_id (root) — remap to "q".
        parent_id = "q" if parent == plan_id else parent
        if parent_id == "q":
            trace_edges.append(Edge(parent_id, child, EdgeRelation.REQUIRES))
            continue
        child_on_path = child in selected_path
        parent_on_path = parent in selected_path
        if child_on_path and parent_on_path:
            trace_edges.append(Edge(parent, child, EdgeRelation.YIELDS))
        elif selected_path and not child_on_path:
            trace_edges.append(Edge(parent, child, EdgeRelation.CONSIDERS, "alternative"))
        else:
            trace_edges.append(Edge(parent, child, EdgeRelation.CONSIDERS))

    # Emit a conclusion node summarising the beam selection.
    selected_last = next(iter(reversed(list(selected_path))), None) if selected_path else None
    concl_id = "conclusion"
    concl_kind = StepKind.CONCLUSION
    if selected_path:
        steps.append(
            ReasoningStep(
                id=concl_id,
                kind=concl_kind,
                label=f"Selected path: {' → '.join(selected_path)}",
                status=StepStatus.OK,
                detail="Top beam-search score.",
            )
        )
        if selected_last is not None:
            trace_edges.append(Edge(selected_last, concl_id, EdgeRelation.YIELDS))
        verdict = "plan-selected"
        summary = f"Beam search selected {len(selected_path)}-step path."
    else:
        steps.append(
            ReasoningStep(
                id=concl_id,
                kind=concl_kind,
                label="No path selected yet",
                status=StepStatus.PENDING,
                detail="Beam search did not produce a complete path.",
            )
        )
        trace_edges.append(Edge("q", concl_id, EdgeRelation.YIELDS))
        verdict = "plan-pending"
        summary = "No complete root-to-leaf path yet."

    trace = DecisionTrace(
        id=trace_id,
        title=title,
        question=question,
        source="praxis",
        kind="plan",
        root="q",
        steps=steps,
        edges=trace_edges,
        outcome=Outcome(
            verdict=verdict,
            summary=summary,
            meta={"plan_id": plan_id, "branches": len(nodes), "selected": len(selected_path)},
        ),
        tags=["praxis", "plan"],
    )
    trace.validate()
    return trace


# ---------------------------------------------------------------------------
# Telos AlignmentResult → DecisionTrace
# ---------------------------------------------------------------------------

class _AlignmentResult(Protocol):
    aligned: bool
    drift_score: float
    reason: str | None


def trace_from_telos_drift(
    result: _AlignmentResult,
    *,
    action_description: str,
    active_goals: Sequence[Mapping[str, Any]] = (),
    conflicts: Sequence[Mapping[str, Any]] = (),
    threshold: float = 0.3,
    question: str | None = None,
    title: str | None = None,
    trace_id: str | None = None,
) -> DecisionTrace:
    """Build a DecisionTrace from a Telos ``AlignmentResult``.

    Arguments:
        result: ``AlignmentResult``-shaped object (aligned, drift_score, reason).
        action_description: The action Telos was asked to check.
        active_goals: List of ``{goal_id, description}`` dicts for the currently
            active GoalContracts. Rendered as premises.
        conflicts: Optional ``[{"goal_id", "postcondition", "score"}, ...]``
            list — if present, each becomes a constraint node connected to the
            offending observation.
        threshold: Conflict threshold (for display; default matches Telos).
    """
    trace_id = trace_id or f"telos-drift-{uuid4().hex[:12]}"
    verdict_word = "aligned" if result.aligned else "drift"
    title = title or f"Telos alignment — {verdict_word.upper()}"
    question = question or "Is the agent still aligned with its declared goals?"

    steps: list[ReasoningStep] = [
        ReasoningStep(
            id="q",
            kind=StepKind.QUESTION,
            label=question,
            source_ref="services/telos/src/telos/core.py",
        ),
        ReasoningStep(
            id="action",
            kind=StepKind.OBSERVATION,
            label=f"Proposed action: {action_description}",
            status=StepStatus.INFO,
        ),
    ]
    edges: list[Edge] = [Edge("q", "action", EdgeRelation.CONSIDERS)]

    for i, goal in enumerate(active_goals):
        gid = f"goal.{i}"
        description = str(goal.get("description") or goal.get("goal_id") or f"goal-{i}")
        steps.append(
            ReasoningStep(
                id=gid,
                kind=StepKind.PREMISE,
                label=f"Active goal: {description}",
                status=StepStatus.OK,
                meta={"goal_id": goal.get("goal_id")},
            )
        )
        edges.append(Edge("q", gid, EdgeRelation.REQUIRES))

    for i, conflict in enumerate(conflicts):
        cid = f"conflict.{i}"
        pc = str(conflict.get("postcondition") or "")
        score = float(conflict.get("score") or 0.0)
        steps.append(
            ReasoningStep(
                id=cid,
                kind=StepKind.CONSTRAINT,
                label=f"Postcondition: {pc}",
                detail=f"similarity = {score:.2f}  (threshold {threshold:.2f})",
                status=StepStatus.FAILED,
                confidence=score,
                meta={"goal_id": conflict.get("goal_id"), "score": score},
            )
        )
        edges.append(Edge("action", cid, EdgeRelation.CONTRADICTS, f"sim={score:.2f}"))
        # Link back to the goal that owns this postcondition if we can.
        goal_id = conflict.get("goal_id")
        for j, goal in enumerate(active_goals):
            if goal.get("goal_id") == goal_id:
                edges.append(Edge(f"goal.{j}", cid, EdgeRelation.REQUIRES, "postcondition"))
                break

    drift_id = "drift"
    drift_status = StepStatus.TRIGGERED if not result.aligned else StepStatus.OK
    steps.append(
        ReasoningStep(
            id=drift_id,
            kind=StepKind.INFERENCE,
            label=f"Drift score: {result.drift_score:.2f} (threshold {threshold:.2f})",
            status=drift_status,
            confidence=result.drift_score,
            detail=result.reason,
        )
    )
    if conflicts:
        for i in range(len(conflicts)):
            edges.append(Edge(f"conflict.{i}", drift_id, EdgeRelation.SUPPORTS))
    else:
        edges.append(Edge("action", drift_id, EdgeRelation.SUPPORTS))

    concl_id = "conclusion"
    concl_status = StepStatus.OK if result.aligned else StepStatus.FAILED
    steps.append(
        ReasoningStep(
            id=concl_id,
            kind=StepKind.CONCLUSION,
            label=("Aligned — action is consistent with goals"
                   if result.aligned else "Drift detected — escalate to operator"),
            status=concl_status,
            detail=result.reason,
        )
    )
    edges.append(Edge(drift_id, concl_id, EdgeRelation.YIELDS))

    trace = DecisionTrace(
        id=trace_id,
        title=title,
        question=question,
        source="telos",
        kind="goal",
        root="q",
        steps=steps,
        edges=edges,
        outcome=Outcome(
            verdict="aligned" if result.aligned else "drift",
            summary=result.reason or (
                "No drift detected." if result.aligned
                else f"Drift score {result.drift_score:.2f} exceeds threshold."
            ),
            confidence=result.drift_score,
            meta={"threshold": threshold, "drift_score": result.drift_score},
        ),
        tags=["telos", "goal", verdict_word],
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


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _default_reason(decision: str, n_violations: int) -> str:
    if decision == "allow":
        return "No rules triggered."
    if decision == "review_required":
        return f"{n_violations} warning-level rule(s) triggered — human review needed."
    if decision == "block":
        return f"{n_violations} rule violation(s); at least one at error severity."
    return "Decision produced."
