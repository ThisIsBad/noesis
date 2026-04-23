"""Pattern-based queries over DecisionTrace collections.

Goes beyond the simple query-string filters on ``GET /api/traces`` by
letting callers specify *step* and *edge* predicates — e.g. "every
trace where a rule_check step named `no_unauthorized_destruction`
triggered", or "every trace with an edge of relation `contradicts`
pointing at a conclusion".

A query is a JSON document::

    {
        "any_step": [
            {"kind": "rule_check", "status": "triggered",
             "label_contains": "no_unauthorized"}
        ],
        "any_edge": [
            {"relation": "contradicts"}
        ],
        "all_steps": [ ... ],
        "source": "logos"
    }

- ``any_step``/``any_edge``: the trace matches if *any* of its steps /
  edges match *any* predicate in the list (OR across predicates + OR
  across traversal, within each clause).
- ``all_steps``/``all_edges``: every predicate must be satisfied by
  *some* step/edge in the trace (AND across predicates).
- Scalar fields (``source``, ``kind``, ``verdict``, etc.) behave exactly
  like the simple filters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from theoria.filters import TraceFilter
from theoria.models import DecisionTrace, Edge, ReasoningStep


@dataclass(frozen=True)
class StepPredicate:
    """One step-level predicate. All fields AND together."""

    id: str | None = None
    kind: str | None = None
    status: str | None = None
    label_contains: str | None = None        # case-insensitive
    detail_contains: str | None = None
    confidence_gte: float | None = None
    confidence_lte: float | None = None

    def matches(self, step: ReasoningStep) -> bool:
        if self.id is not None and step.id != self.id:
            return False
        if self.kind is not None and step.kind.value != self.kind:
            return False
        if self.status is not None and step.status.value != self.status:
            return False
        if self.label_contains is not None:
            if self.label_contains.lower() not in (step.label or "").lower():
                return False
        if self.detail_contains is not None:
            if self.detail_contains.lower() not in (step.detail or "").lower():
                return False
        if self.confidence_gte is not None:
            if step.confidence is None or step.confidence < self.confidence_gte:
                return False
        if self.confidence_lte is not None:
            if step.confidence is None or step.confidence > self.confidence_lte:
                return False
        return True


@dataclass(frozen=True)
class EdgePredicate:
    """One edge-level predicate. All fields AND together."""

    source: str | None = None
    target: str | None = None
    relation: str | None = None
    label_contains: str | None = None        # case-insensitive

    def matches(self, edge: Edge) -> bool:
        if self.source is not None and edge.source != self.source:
            return False
        if self.target is not None and edge.target != self.target:
            return False
        if self.relation is not None and edge.relation.value != self.relation:
            return False
        if self.label_contains is not None:
            needle = self.label_contains.lower()
            if needle not in (edge.label or "").lower():
                return False
        return True


@dataclass(frozen=True)
class TraceQuery:
    """Full trace-level query."""

    base: TraceFilter = field(default_factory=TraceFilter)
    any_step: Sequence[StepPredicate] = ()
    all_steps: Sequence[StepPredicate] = ()
    any_edge: Sequence[EdgePredicate] = ()
    all_edges: Sequence[EdgePredicate] = ()

    def matches(self, trace: DecisionTrace) -> bool:
        if not self.base.matches(trace):
            return False
        if self.any_step:
            if not any(p.matches(s) for p in self.any_step for s in trace.steps):
                return False
        if self.all_steps:
            for step_pred in self.all_steps:
                if not any(step_pred.matches(s) for s in trace.steps):
                    return False
        if self.any_edge:
            if not any(p.matches(e) for p in self.any_edge for e in trace.edges):
                return False
        if self.all_edges:
            for edge_pred in self.all_edges:
                if not any(edge_pred.matches(e) for e in trace.edges):
                    return False
        return True


def run_query(
    traces: Iterable[DecisionTrace],
    query: TraceQuery,
    *,
    limit: int | None = None,
) -> list[DecisionTrace]:
    """Apply a compiled query; cap results at ``limit`` if provided."""
    out: list[DecisionTrace] = []
    for trace in traces:
        if query.matches(trace):
            out.append(trace)
            if limit is not None and len(out) >= limit:
                break
    return out


# ---------------------------------------------------------------------------
# JSON → TraceQuery parser
# ---------------------------------------------------------------------------

_STEP_FIELDS = {
    "id", "kind", "status", "label_contains", "detail_contains",
    "confidence_gte", "confidence_lte",
}
_EDGE_FIELDS = {"source", "target", "relation", "label_contains"}
_BASE_FIELDS = {"source", "kind", "verdict", "tags", "text", "q"}


def parse_query(payload: Mapping[str, Any]) -> TraceQuery:
    """Parse a JSON-style dict into a ``TraceQuery``.

    Unknown keys in a predicate raise ``ValueError`` so typos don't silently
    produce queries that match everything.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("query must be a JSON object")

    base_dict: dict[str, Any] = {}
    for key in ("source", "kind", "verdict"):
        if key in payload:
            base_dict[key] = payload[key]
    tags = payload.get("tags") or payload.get("tag") or ()
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    if tags:
        base_dict["tags"] = tuple(tags)
    if "q" in payload:
        base_dict["text"] = payload["q"]
    elif "text" in payload:
        base_dict["text"] = payload["text"]
    base = TraceFilter(**base_dict)

    any_step = tuple(_parse_step_predicate(p) for p in payload.get("any_step", ()))
    all_steps = tuple(_parse_step_predicate(p) for p in payload.get("all_steps", ()))
    any_edge = tuple(_parse_edge_predicate(p) for p in payload.get("any_edge", ()))
    all_edges = tuple(_parse_edge_predicate(p) for p in payload.get("all_edges", ()))

    return TraceQuery(
        base=base,
        any_step=any_step,
        all_steps=all_steps,
        any_edge=any_edge,
        all_edges=all_edges,
    )


def _parse_step_predicate(raw: Any) -> StepPredicate:
    if not isinstance(raw, Mapping):
        raise ValueError(f"step predicate must be an object, got {type(raw).__name__}")
    unknown = set(raw.keys()) - _STEP_FIELDS
    if unknown:
        raise ValueError(f"unknown step-predicate fields: {sorted(unknown)}")
    kwargs: dict[str, Any] = dict(raw)
    for key in ("confidence_gte", "confidence_lte"):
        if key in kwargs and kwargs[key] is not None:
            kwargs[key] = float(kwargs[key])
    return StepPredicate(**kwargs)


def _parse_edge_predicate(raw: Any) -> EdgePredicate:
    if not isinstance(raw, Mapping):
        raise ValueError(f"edge predicate must be an object, got {type(raw).__name__}")
    unknown = set(raw.keys()) - _EDGE_FIELDS
    if unknown:
        raise ValueError(f"unknown edge-predicate fields: {sorted(unknown)}")
    return EdgePredicate(**dict(raw))


__all__: Sequence[str] = (
    "StepPredicate", "EdgePredicate", "TraceQuery",
    "run_query", "parse_query",
)
