"""Structural diff between two DecisionTraces.

Use cases:
    - "How did the reasoning change after we added policy rule X?"
    - "Compare a successful plan to the failed one."
    - Track trace drift over repeated decisions on the same question.

The diff is structural (by step id + edge triple) — it does not try to
align semantically different traces. That's by design: Theoria treats
step IDs as meaningful (Logos and the other adapters always produce
stable IDs like ``rule.0`` or ``fact.destructive``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from theoria.export import _md_code, _md_escape
from theoria.models import DecisionTrace, Edge, EdgeRelation, ReasoningStep, StepKind, StepStatus

# Fields on a ReasoningStep that, when they differ, count as a "change".
_STEP_COMPARE_FIELDS: tuple[str, ...] = (
    "kind",
    "label",
    "detail",
    "status",
    "confidence",
    "source_ref",
    "meta",
)


@dataclass
class StepChange:
    """A step whose id exists in both traces but whose fields differ."""

    id: str
    old: ReasoningStep
    new: ReasoningStep
    field_changes: dict[str, tuple[Any, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "old": self.old.to_dict(),
            "new": self.new.to_dict(),
            "field_changes": {k: [_scalar(v[0]), _scalar(v[1])] for k, v in self.field_changes.items()},
        }


@dataclass
class TraceDiff:
    """Diff result between trace ``a`` (baseline) and trace ``b`` (new)."""

    a_id: str
    b_id: str
    added_steps: list[ReasoningStep] = field(default_factory=list)
    removed_steps: list[ReasoningStep] = field(default_factory=list)
    changed_steps: list[StepChange] = field(default_factory=list)
    unchanged_step_ids: list[str] = field(default_factory=list)
    added_edges: list[Edge] = field(default_factory=list)
    removed_edges: list[Edge] = field(default_factory=list)
    outcome_change: tuple[dict[str, Any] | None, dict[str, Any] | None] | None = None

    # Whole-trace metadata so consumers don't have to re-fetch.
    a_title: str = ""
    b_title: str = ""

    @property
    def is_empty(self) -> bool:
        return not (
            self.added_steps
            or self.removed_steps
            or self.changed_steps
            or self.added_edges
            or self.removed_edges
            or self.outcome_change
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "a_id": self.a_id,
            "b_id": self.b_id,
            "a_title": self.a_title,
            "b_title": self.b_title,
            "added_steps": [s.to_dict() for s in self.added_steps],
            "removed_steps": [s.to_dict() for s in self.removed_steps],
            "changed_steps": [c.to_dict() for c in self.changed_steps],
            "unchanged_step_ids": list(self.unchanged_step_ids),
            "added_edges": [e.to_dict() for e in self.added_edges],
            "removed_edges": [e.to_dict() for e in self.removed_edges],
            "outcome_change": _outcome_change_payload(self.outcome_change),
            "is_empty": self.is_empty,
        }


def diff_traces(a: DecisionTrace, b: DecisionTrace) -> TraceDiff:
    """Compare two traces structurally."""
    a_steps = {s.id: s for s in a.steps}
    b_steps = {s.id: s for s in b.steps}
    a_ids = set(a_steps)
    b_ids = set(b_steps)

    added = [s for s in b.steps if s.id not in a_ids]
    removed = [s for s in a.steps if s.id not in b_ids]

    changed: list[StepChange] = []
    unchanged: list[str] = []
    for step_id in (s.id for s in b.steps if s.id in a_ids):
        old = a_steps[step_id]
        new = b_steps[step_id]
        field_changes = _compare_step_fields(old, new)
        if field_changes:
            changed.append(StepChange(id=step_id, old=old, new=new, field_changes=field_changes))
        else:
            unchanged.append(step_id)

    a_edge_set = {_edge_key(e): e for e in a.edges}
    b_edge_set = {_edge_key(e): e for e in b.edges}
    added_edges = [b_edge_set[k] for k in b_edge_set.keys() - a_edge_set.keys()]
    removed_edges = [a_edge_set[k] for k in a_edge_set.keys() - b_edge_set.keys()]

    outcome_change: tuple[dict[str, Any] | None, dict[str, Any] | None] | None = None
    a_out = a.outcome.to_dict() if a.outcome else None
    b_out = b.outcome.to_dict() if b.outcome else None
    if a_out != b_out:
        outcome_change = (a_out, b_out)

    return TraceDiff(
        a_id=a.id,
        b_id=b.id,
        a_title=a.title,
        b_title=b.title,
        added_steps=added,
        removed_steps=removed,
        changed_steps=changed,
        unchanged_step_ids=unchanged,
        added_edges=added_edges,
        removed_edges=removed_edges,
        outcome_change=outcome_change,
    )


def _compare_step_fields(old: ReasoningStep, new: ReasoningStep) -> dict[str, tuple[Any, Any]]:
    changes: dict[str, tuple[Any, Any]] = {}
    for name in _STEP_COMPARE_FIELDS:
        a_val = getattr(old, name)
        b_val = getattr(new, name)
        if isinstance(a_val, StepKind) or isinstance(a_val, StepStatus):
            a_val, b_val = a_val.value, b_val.value
        if a_val != b_val:
            changes[name] = (a_val, b_val)
    return changes


def _edge_key(edge: Edge) -> tuple[str, str, str]:
    return (edge.source, edge.target, edge.relation.value)


def _scalar(value: Any) -> Any:
    """Serialize enum/complex values to something JSON-friendly."""
    if isinstance(value, (StepKind, StepStatus, EdgeRelation)):
        return value.value
    if isinstance(value, dict):
        return {k: _scalar(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scalar(v) for v in value]
    return value


def _outcome_change_payload(
    change: tuple[dict[str, Any] | None, dict[str, Any] | None] | None,
) -> dict[str, Any] | None:
    if change is None:
        return None
    return {"old": change[0], "new": change[1]}


# ---------------------------------------------------------------------------
# Markdown rendering of a diff
# ---------------------------------------------------------------------------


def diff_to_markdown(diff: TraceDiff, *, embed_mermaid: bool = True) -> str:
    lines: list[str] = [
        f"# Trace diff: {_md_escape(diff.a_title or diff.a_id)} → {_md_escape(diff.b_title or diff.b_id)}",
        "",
        "| Field | Baseline (a) | New (b) |",
        "|-------|--------------|---------|",
        f"| Trace ID | {_md_code(diff.a_id)} | {_md_code(diff.b_id)} |",
        f"| Title | {_md_escape(diff.a_title)} | {_md_escape(diff.b_title)} |",
        f"| +Steps | — | **{len(diff.added_steps)}** |",
        f"| −Steps | **{len(diff.removed_steps)}** | — |",
        f"| ~Steps | — | **{len(diff.changed_steps)}** |",
        f"| +Edges | — | **{len(diff.added_edges)}** |",
        f"| −Edges | **{len(diff.removed_edges)}** | — |",
        "",
    ]

    if diff.is_empty:
        lines.extend(["_No structural changes — traces are equivalent._", ""])
        return "\n".join(lines).rstrip() + "\n"

    if embed_mermaid:
        lines.extend(["## Merged diff graph", "", "```mermaid", diff_to_mermaid(diff).rstrip(), "```", ""])

    if diff.added_steps:
        lines.extend(["## Added steps", ""])
        for step in diff.added_steps:
            lines.append(
                f"- {_md_code(step.id)} — **{step.kind.value}** ({step.status.value}) — {_md_escape(step.label)}"
            )
        lines.append("")

    if diff.removed_steps:
        lines.extend(["## Removed steps", ""])
        for step in diff.removed_steps:
            lines.append(
                f"- {_md_code(step.id)} — **{step.kind.value}** ({step.status.value}) — {_md_escape(step.label)}"
            )
        lines.append("")

    if diff.changed_steps:
        lines.extend(["## Changed steps", ""])
        for change in diff.changed_steps:
            lines.append(f"### {_md_code(change.id)}")
            lines.append("")
            lines.append("| Field | Before | After |")
            lines.append("|-------|--------|-------|")
            for fname, (old_v, new_v) in change.field_changes.items():
                lines.append(f"| {_md_escape(fname)} | {_md_code(_stringify(old_v))} | {_md_code(_stringify(new_v))} |")
            lines.append("")

    if diff.added_edges:
        lines.extend(["## Added edges", ""])
        for edge in diff.added_edges:
            lines.append(
                f"- {_md_code(edge.source)} → {_md_code(edge.target)} "
                f"({edge.relation.value})" + (f" — *{_md_escape(edge.label)}*" if edge.label else "")
            )
        lines.append("")

    if diff.removed_edges:
        lines.extend(["## Removed edges", ""])
        for edge in diff.removed_edges:
            lines.append(
                f"- {_md_code(edge.source)} → {_md_code(edge.target)} "
                f"({edge.relation.value})" + (f" — *{_md_escape(edge.label)}*" if edge.label else "")
            )
        lines.append("")

    if diff.outcome_change is not None:
        old_out, new_out = diff.outcome_change
        lines.extend(["## Outcome change", ""])
        lines.append(f"- **Before:** {_md_code(old_out) if old_out else '_none_'}")
        lines.append(f"- **After:**  {_md_code(new_out) if new_out else '_none_'}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _stringify(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list, tuple)):
        import json as _json

        return _json.dumps(_scalar(value), sort_keys=True)
    return str(value)


# ---------------------------------------------------------------------------
# Mermaid rendering: merged graph with add/remove/change colouring
# ---------------------------------------------------------------------------

_DIFF_CLASS_DEFS = [
    "classDef same fill:#1b242d,stroke:#6f7a8a,color:#e6edf3",
    "classDef added fill:#12321f,stroke:#7ee787,color:#e6edf3",
    "classDef removed fill:#3a1a1a,stroke:#ff6b6b,color:#e6edf3",
    "classDef changed fill:#332f14,stroke:#f5a623,color:#e6edf3",
]


def diff_to_mermaid(diff: TraceDiff) -> str:
    lines: list[str] = ["%% Trace diff", "flowchart TD"]

    union_steps: dict[str, tuple[ReasoningStep, str]] = {}
    for step in diff.removed_steps:
        union_steps[step.id] = (step, "removed")
    for change in diff.changed_steps:
        # Show the "new" version when rendering a changed node.
        union_steps[change.new.id] = (change.new, "changed")
    for step in diff.added_steps:
        union_steps[step.id] = (step, "added")
    # Fill in unchanged nodes (they appear in unchanged_step_ids — we need a
    # ReasoningStep to render, but we don't carry those here; caller can
    # render against the merged graph using the 'same' class.). We skip them
    # to keep the diff graph focused on what changed.
    unchanged_seed = {
        sid: None
        for sid in diff.unchanged_step_ids
        # skip — no ReasoningStep to render; unchanged stuff is visual clutter
    }
    _ = unchanged_seed

    for sid, (step, klass) in union_steps.items():
        nid = _mermaid_id(sid)
        marker = {"added": "[+] ", "removed": "[−] ", "changed": "[~] "}[klass]
        label = f'"{marker}{_mermaid_escape(step.label)}"'
        lines.append(f"    {nid}[{label}]")
        lines.append(f"    class {nid} {klass}")

    edge_classes: list[tuple[Edge, str]] = []
    edge_classes.extend((e, "added") for e in diff.added_edges)
    edge_classes.extend((e, "removed") for e in diff.removed_edges)
    for edge, klass in edge_classes:
        src = _mermaid_id(edge.source)
        tgt = _mermaid_id(edge.target)
        arrow = "==>" if klass == "added" else "-.->"
        label = f"|{_mermaid_escape(edge.label)}|" if edge.label else ""
        lines.append(f"    {src} {arrow}{label} {tgt}")

    lines.append("")
    lines.extend(f"    {d}" for d in _DIFF_CLASS_DEFS)
    return "\n".join(lines) + "\n"


_ID_REPLACE = str.maketrans({c: "_" for c in ". -:/"})


def _mermaid_id(raw: str) -> str:
    clean = raw.translate(_ID_REPLACE)
    if not clean or not (clean[0].isalpha() or clean[0] == "_"):
        clean = "n_" + clean
    return clean


def _mermaid_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', "&quot;").replace("|", "&#124;").replace("\n", " ")


__all__: Sequence[str] = ("diff_traces", "diff_to_markdown", "diff_to_mermaid", "TraceDiff", "StepChange")
