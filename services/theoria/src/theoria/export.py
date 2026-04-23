"""Export a DecisionTrace to Mermaid or Graphviz DOT.

These exports make decision traces pasteable into PR descriptions,
Slack, architecture docs, and any other surface that renders Mermaid
or DOT — no Theoria server required at the reading end.
"""

from __future__ import annotations

import re
from typing import Iterable

from theoria.models import DecisionTrace, Edge, EdgeRelation, ReasoningStep, StepKind, StepStatus

# ---------------------------------------------------------------------------
# Mermaid
# ---------------------------------------------------------------------------

# Kind → node shape (Mermaid flowchart syntax).
# Mermaid doesn't support every StepKind distinctly so we collapse some.
_MERMAID_SHAPE: dict[StepKind, tuple[str, str]] = {
    StepKind.QUESTION:       ("([", "])"),     # stadium
    StepKind.PREMISE:        ("[", "]"),
    StepKind.OBSERVATION:    ("[/", "/]"),     # parallelogram
    StepKind.RULE_CHECK:     ("{{", "}}"),     # hexagon
    StepKind.CONSTRAINT:     ("{{", "}}"),
    StepKind.INFERENCE:      ("[", "]"),
    StepKind.EVIDENCE:       ("[\\", "\\]"),   # parallelogram (alt)
    StepKind.ALTERNATIVE:    ("[[", "]]"),     # subroutine
    StepKind.COUNTERFACTUAL: ("[[", "]]"),
    StepKind.CONCLUSION:     ("([", "])"),     # stadium
    StepKind.NOTE:           ("[", "]"),
}

_STATUS_CLASS: dict[StepStatus, str] = {
    StepStatus.OK: "ok",
    StepStatus.TRIGGERED: "triggered",
    StepStatus.FAILED: "failed",
    StepStatus.REJECTED: "rejected",
    StepStatus.PENDING: "pending",
    StepStatus.UNKNOWN: "unknown",
    StepStatus.INFO: "info",
}

_MERMAID_CLASS_DEFS = [
    "classDef ok fill:#12321f,stroke:#7ee787,color:#e6edf3",
    "classDef triggered fill:#3a2a12,stroke:#f5a623,color:#e6edf3",
    "classDef failed fill:#3a1a1a,stroke:#ff6b6b,color:#e6edf3",
    "classDef rejected fill:#2a1f3a,stroke:#b388eb,color:#e6edf3",
    "classDef pending fill:#332f14,stroke:#d1c44b,color:#e6edf3",
    "classDef unknown fill:#1f2630,stroke:#6f7a8a,color:#e6edf3",
    "classDef info fill:#1b242d,stroke:#79c0ff,color:#e6edf3",
]


def to_mermaid(trace: DecisionTrace) -> str:
    """Render ``trace`` as a Mermaid ``flowchart TD`` string."""
    lines: list[str] = [f"%% {trace.title}", "flowchart TD"]

    for step in trace.steps:
        sid = _sanitize_id(step.id)
        open_tag, close_tag = _MERMAID_SHAPE.get(step.kind, ("[", "]"))
        label = _mermaid_label(step)
        lines.append(f"    {sid}{open_tag}{label}{close_tag}")

    for step in trace.steps:
        sid = _sanitize_id(step.id)
        cls = _STATUS_CLASS[step.status]
        lines.append(f"    class {sid} {cls}")

    for edge in trace.edges:
        src = _sanitize_id(edge.source)
        tgt = _sanitize_id(edge.target)
        arrow, lbl = _mermaid_arrow(edge)
        if lbl:
            lines.append(f"    {src} {arrow}|{_mermaid_escape(lbl)}| {tgt}")
        else:
            lines.append(f"    {src} {arrow} {tgt}")

    lines.append("")
    lines.extend(f"    {d}" for d in _MERMAID_CLASS_DEFS)
    return "\n".join(lines) + "\n"


def _mermaid_label(step: ReasoningStep) -> str:
    kind = step.kind.value.replace("_", " ")
    parts = [f"<b>{_mermaid_escape(step.label)}</b>", f"<i>{kind} · {step.status.value}</i>"]
    if step.confidence is not None:
        parts.append(f"confidence: {step.confidence * 100:.0f}%")
    return '"' + "<br/>".join(parts) + '"'


def _mermaid_arrow(edge: Edge) -> tuple[str, str | None]:
    relation = edge.relation
    label = edge.label or (relation.value if relation is not EdgeRelation.SUPPORTS else None)
    if relation in (EdgeRelation.CONTRADICTS, EdgeRelation.PRUNES):
        return "-.->", label
    if relation in (EdgeRelation.IMPLIES, EdgeRelation.YIELDS):
        return "==>", label
    return "-->", label


def _mermaid_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace('"', "&quot;")
        .replace("|", "&#124;")
        .replace("\n", " ")
    )


# ---------------------------------------------------------------------------
# Graphviz DOT
# ---------------------------------------------------------------------------

_DOT_FILL: dict[StepStatus, tuple[str, str]] = {
    StepStatus.OK: ("#12321f", "#7ee787"),
    StepStatus.TRIGGERED: ("#3a2a12", "#f5a623"),
    StepStatus.FAILED: ("#3a1a1a", "#ff6b6b"),
    StepStatus.REJECTED: ("#2a1f3a", "#b388eb"),
    StepStatus.PENDING: ("#332f14", "#d1c44b"),
    StepStatus.UNKNOWN: ("#1f2630", "#6f7a8a"),
    StepStatus.INFO: ("#1b242d", "#79c0ff"),
}

_DOT_SHAPE: dict[StepKind, str] = {
    StepKind.QUESTION: "oval",
    StepKind.PREMISE: "box",
    StepKind.OBSERVATION: "parallelogram",
    StepKind.RULE_CHECK: "hexagon",
    StepKind.CONSTRAINT: "hexagon",
    StepKind.INFERENCE: "box",
    StepKind.EVIDENCE: "parallelogram",
    StepKind.ALTERNATIVE: "component",
    StepKind.COUNTERFACTUAL: "component",
    StepKind.CONCLUSION: "oval",
    StepKind.NOTE: "note",
}


def to_graphviz(trace: DecisionTrace) -> str:
    """Render ``trace`` as a Graphviz ``digraph`` DOT string."""
    lines: list[str] = [f"// {trace.title}", "digraph Trace {",
                        "    rankdir=TB;",
                        '    bgcolor="#0c1116";',
                        '    node [fontname="Inter" fontcolor="#e6edf3" style=filled];',
                        '    edge [color="#8b98a5" fontcolor="#8b98a5" fontname="Inter"];']

    for step in trace.steps:
        nid = _dot_id(step.id)
        fill, stroke = _DOT_FILL[step.status]
        shape = _DOT_SHAPE.get(step.kind, "box")
        label = _dot_label(step)
        lines.append(
            f'    {nid} [shape={shape} label="{label}" fillcolor="{fill}" color="{stroke}"];'
        )

    for edge in trace.edges:
        src = _dot_id(edge.source)
        tgt = _dot_id(edge.target)
        style, color = _dot_edge_style(edge)
        label = edge.label or ""
        attrs: list[str] = [f'color="{color}"']
        if style:
            attrs.append(f'style="{style}"')
        if label:
            attrs.append(f'label="{_dot_escape(label)}"')
        lines.append(f"    {src} -> {tgt} [{' '.join(attrs)}];")

    lines.append("}")
    return "\n".join(lines) + "\n"


def _dot_label(step: ReasoningStep) -> str:
    kind = step.kind.value.replace("_", " ")
    lines = [_dot_escape(step.label), f"({kind} · {step.status.value})"]
    if step.confidence is not None:
        lines.append(f"confidence: {step.confidence * 100:.0f}%")
    return "\\n".join(lines)


def _dot_edge_style(edge: Edge) -> tuple[str | None, str]:
    rel = edge.relation
    if rel is EdgeRelation.CONTRADICTS or rel is EdgeRelation.PRUNES:
        return "dashed", "#ff6b6b"
    if rel is EdgeRelation.IMPLIES or rel is EdgeRelation.YIELDS:
        return "bold", "#7ee787"
    if rel is EdgeRelation.REQUIRES:
        return "dashed", "#9ecbff"
    if rel is EdgeRelation.CONSIDERS:
        return "dashed", "#b388eb"
    if rel is EdgeRelation.WITNESS:
        return None, "#f5a623"
    return None, "#56d4dd"


def _dot_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


# ---------------------------------------------------------------------------
# Identifier sanitization — shared
# ---------------------------------------------------------------------------

_ID_SAFE = re.compile(r"[^A-Za-z0-9_]")


def _sanitize_id(raw: str) -> str:
    """Produce a Mermaid-safe identifier from a free-form step id."""
    clean = _ID_SAFE.sub("_", raw)
    if not clean or not clean[0].isalpha() and clean[0] != "_":
        clean = "n_" + clean
    return clean


def _dot_id(raw: str) -> str:
    """DOT allows quoted identifiers — safest to quote."""
    return '"' + raw.replace("\\", "\\\\").replace('"', '\\"') + '"'


def format_for(trace: DecisionTrace, fmt: str) -> str:
    """Dispatch helper — ``fmt`` in ``{"mermaid", "dot", "graphviz"}``."""
    fmt = fmt.lower()
    if fmt == "mermaid":
        return to_mermaid(trace)
    if fmt in ("dot", "graphviz"):
        return to_graphviz(trace)
    raise ValueError(f"unknown export format: {fmt!r}")


__all__: Iterable[str] = ("to_mermaid", "to_graphviz", "format_for")
