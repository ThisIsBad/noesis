"""Decision-trace schema.

A ``DecisionTrace`` is a DAG of ``ReasoningStep`` nodes that records how
a decision was reached — the premises considered, the rules/constraints
evaluated, the evidence weighed, the alternatives pruned, and the final
conclusion. The schema is intentionally service-agnostic so traces from
Logos, Praxis, Telos, Kosmos, etc. share one visualization surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable


class StepKind(str, Enum):
    """Kind of reasoning step — drives node shape / colour in the UI."""

    QUESTION = "question"
    PREMISE = "premise"
    OBSERVATION = "observation"
    RULE_CHECK = "rule_check"
    CONSTRAINT = "constraint"
    INFERENCE = "inference"
    EVIDENCE = "evidence"
    ALTERNATIVE = "alternative"
    COUNTERFACTUAL = "counterfactual"
    CONCLUSION = "conclusion"
    NOTE = "note"


class StepStatus(str, Enum):
    """Evaluation status of a reasoning step."""

    OK = "ok"                    # satisfied / accepted / true
    TRIGGERED = "triggered"      # rule fired / constraint active
    FAILED = "failed"            # constraint violated / proof failed
    REJECTED = "rejected"        # branch pruned / alternative discarded
    PENDING = "pending"          # not yet evaluated
    UNKNOWN = "unknown"          # solver returned UNKNOWN / no verdict
    INFO = "info"                # informational, no verdict


class EdgeRelation(str, Enum):
    """How a child step relates to its parent."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    IMPLIES = "implies"
    REQUIRES = "requires"
    CONSIDERS = "considers"       # branch being explored
    PRUNES = "prunes"             # alternative was discarded
    YIELDS = "yields"             # produced as output
    WITNESS = "witness"           # concrete example / Z3 model


@dataclass
class Edge:
    """Directed edge in the reasoning DAG."""

    source: str
    target: str
    relation: EdgeRelation = EdgeRelation.SUPPORTS
    label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation.value,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Edge":
        return cls(
            source=str(payload["source"]),
            target=str(payload["target"]),
            relation=EdgeRelation(payload.get("relation", "supports")),
            label=payload.get("label"),
        )


@dataclass
class ReasoningStep:
    """One node in the reasoning DAG."""

    id: str
    kind: StepKind
    label: str
    detail: str | None = None
    status: StepStatus = StepStatus.INFO
    confidence: float | None = None
    source_ref: str | None = None        # e.g. "logos/action_policy.py:145"
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "label": self.label,
            "detail": self.detail,
            "status": self.status.value,
            "confidence": self.confidence,
            "source_ref": self.source_ref,
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReasoningStep":
        if "id" not in payload or "label" not in payload or "kind" not in payload:
            raise ValueError("ReasoningStep requires 'id', 'kind', 'label'")
        return cls(
            id=str(payload["id"]),
            kind=StepKind(payload["kind"]),
            label=str(payload["label"]),
            detail=payload.get("detail"),
            status=StepStatus(payload.get("status", "info")),
            confidence=_optional_float(payload.get("confidence")),
            source_ref=payload.get("source_ref"),
            meta=dict(payload.get("meta") or {}),
        )


@dataclass
class Outcome:
    """Final decision outcome for a trace."""

    verdict: str                         # free-form: "allow", "block", "plan-found", ...
    summary: str
    confidence: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Outcome":
        return cls(
            verdict=str(payload["verdict"]),
            summary=str(payload.get("summary", "")),
            confidence=_optional_float(payload.get("confidence")),
            meta=dict(payload.get("meta") or {}),
        )


@dataclass
class DecisionTrace:
    """Top-level decision trace: DAG of reasoning steps plus metadata."""

    id: str
    title: str
    question: str
    source: str                          # service of origin: "logos", "praxis", ...
    kind: str                            # "policy" | "plan" | "proof" | "goal" | ...
    root: str                            # id of the root step (usually a QUESTION)
    steps: list[ReasoningStep] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    outcome: Outcome | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tags: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """Check structural invariants — unique step IDs, valid edges, reachable root."""
        if not self.id:
            raise ValueError("DecisionTrace.id must be non-empty")
        if not self.root:
            raise ValueError("DecisionTrace.root must be non-empty")
        ids = [s.id for s in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate step IDs in trace")
        id_set = set(ids)
        if self.root not in id_set:
            raise ValueError(f"Root id '{self.root}' not in steps")
        for edge in self.edges:
            if edge.source not in id_set:
                raise ValueError(f"Edge source '{edge.source}' not in steps")
            if edge.target not in id_set:
                raise ValueError(f"Edge target '{edge.target}' not in steps")

    def add_step(self, step: ReasoningStep) -> ReasoningStep:
        self.steps.append(step)
        return step

    def connect(
        self,
        source: str,
        target: str,
        relation: EdgeRelation = EdgeRelation.SUPPORTS,
        label: str | None = None,
    ) -> Edge:
        edge = Edge(source=source, target=target, relation=relation, label=label)
        self.edges.append(edge)
        return edge

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "question": self.question,
            "source": self.source,
            "kind": self.kind,
            "root": self.root,
            "steps": [s.to_dict() for s in self.steps],
            "edges": [e.to_dict() for e in self.edges],
            "outcome": self.outcome.to_dict() if self.outcome else None,
            "created_at": self.created_at,
            "tags": list(self.tags),
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DecisionTrace":
        trace = cls(
            id=str(payload["id"]),
            title=str(payload.get("title", payload["id"])),
            question=str(payload.get("question", "")),
            source=str(payload.get("source", "unknown")),
            kind=str(payload.get("kind", "custom")),
            root=str(payload["root"]),
            steps=[ReasoningStep.from_dict(s) for s in payload.get("steps", [])],
            edges=[Edge.from_dict(e) for e in payload.get("edges", [])],
            outcome=Outcome.from_dict(payload["outcome"]) if payload.get("outcome") else None,
            created_at=str(payload.get("created_at") or datetime.now(timezone.utc).isoformat()),
            tags=list(payload.get("tags") or []),
            meta=dict(payload.get("meta") or {}),
        )
        trace.validate()
        return trace


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def trace_from_steps(
    trace_id: str,
    title: str,
    question: str,
    source: str,
    kind: str,
    steps: Iterable[ReasoningStep],
    edges: Iterable[Edge],
    outcome: Outcome | None = None,
    tags: Iterable[str] = (),
    meta: dict[str, Any] | None = None,
) -> DecisionTrace:
    """Convenience builder — first step is treated as the root."""
    step_list = list(steps)
    if not step_list:
        raise ValueError("trace_from_steps requires at least one step")
    trace = DecisionTrace(
        id=trace_id,
        title=title,
        question=question,
        source=source,
        kind=kind,
        root=step_list[0].id,
        steps=step_list,
        edges=list(edges),
        outcome=outcome,
        tags=list(tags),
        meta=dict(meta or {}),
    )
    trace.validate()
    return trace
