"""Export a DecisionTrace to Mermaid, Graphviz DOT, or Markdown.

These exports make decision traces pasteable into PR descriptions,
Slack, architecture docs, and any other surface that renders Mermaid,
DOT, or CommonMark — no Theoria server required at the reading end.
"""

from __future__ import annotations

import re
from typing import Iterable

from theoria.models import DecisionTrace, Edge, EdgeRelation, Outcome, ReasoningStep, StepKind, StepStatus

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


# ---------------------------------------------------------------------------
# Markdown — reviewable narrative with an embedded Mermaid diagram
# ---------------------------------------------------------------------------

# Plain-text status markers (no emoji — the repo avoids them).
_STATUS_MARKER: dict[StepStatus, str] = {
    StepStatus.OK: "OK",
    StepStatus.TRIGGERED: "TRIGGERED",
    StepStatus.FAILED: "FAILED",
    StepStatus.REJECTED: "REJECTED",
    StepStatus.PENDING: "PENDING",
    StepStatus.UNKNOWN: "UNKNOWN",
    StepStatus.INFO: "INFO",
}


def to_markdown(trace: DecisionTrace, *, embed_mermaid: bool = True) -> str:
    """Render ``trace`` as reviewable Markdown.

    GitHub, GitLab, and most modern Markdown renderers expand the
    embedded ```mermaid``` block inline, so the output is immediately
    viewable in a PR description or issue comment with no Theoria
    server at the reading end.
    """
    incoming = _incoming_by_target(trace)
    lines: list[str] = [f"# {_md_escape(trace.title)}", ""]

    lines.extend(_md_metadata_table(trace))
    lines.append("")

    if trace.question:
        lines.extend([f"> **Question:** {_md_escape(trace.question)}", ""])

    if trace.outcome and trace.outcome.summary:
        lines.extend([f"**Summary:** {_md_escape(trace.outcome.summary)}", ""])

    if embed_mermaid:
        lines.extend(["## Reasoning graph", "", "```mermaid"])
        lines.append(to_mermaid(trace).rstrip())
        lines.extend(["```", ""])

    lines.extend(["## Steps", ""])
    for step in _steps_in_topological_order(trace):
        lines.extend(_md_step_block(step, incoming.get(step.id, []), trace))
        lines.append("")

    if trace.outcome is not None:
        lines.extend(_md_outcome_block(trace.outcome))

    if trace.tags:
        lines.extend(["", "## Tags", "", " · ".join(_md_code(t) for t in trace.tags)])

    return "\n".join(lines).rstrip() + "\n"


def _md_metadata_table(trace: DecisionTrace) -> list[str]:
    rows: list[tuple[str, str]] = [
        ("Source", _md_code(trace.source)),
        ("Kind", _md_code(trace.kind)),
    ]
    if trace.outcome is not None:
        rows.append(("Verdict", f"**{_md_code(trace.outcome.verdict)}**"))
        if trace.outcome.confidence is not None:
            rows.append(("Confidence", f"{trace.outcome.confidence * 100:.0f}%"))
    rows.append(("Created", _md_code(trace.created_at)))
    rows.append(("Trace ID", _md_code(trace.id)))

    lines = ["| Field | Value |", "|-------|-------|"]
    lines.extend(f"| {k} | {v} |" for k, v in rows)
    return lines


def _md_step_block(
    step: ReasoningStep,
    incoming_edges: list[Edge],
    trace: DecisionTrace,
) -> list[str]:
    kind_label = step.kind.value.replace("_", " ")
    status_tag = f"**{_STATUS_MARKER[step.status]}**" if step.status in (
        StepStatus.TRIGGERED, StepStatus.FAILED, StepStatus.REJECTED
    ) else _STATUS_MARKER[step.status]
    header = f"### {_md_code(step.id)} — {kind_label} ({status_tag})"
    if step.confidence is not None:
        header += f" — confidence {step.confidence * 100:.0f}%"

    lines = [header, "", f"**{_md_escape(step.label)}**"]
    if step.detail:
        lines.extend(["", _md_escape(step.detail)])
    if step.source_ref:
        lines.extend(["", f"↪ {_md_code(step.source_ref)}"])

    if incoming_edges:
        parts: list[str] = []
        for edge in incoming_edges:
            label = f" *({_md_escape(edge.label)})*" if edge.label else ""
            parts.append(f"{_md_code(edge.source)} — {edge.relation.value}{label}")
        lines.extend(["", "*From:* " + "; ".join(parts)])

    if step.meta:
        pretty = _md_meta_list(step.meta)
        if pretty:
            lines.extend(["", *pretty])

    return lines


def _md_meta_list(meta: dict[str, object]) -> list[str]:
    entries: list[str] = []
    for key, value in meta.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            if not value:
                continue
            rendered = ", ".join(_md_code(v) for v in value)
        elif isinstance(value, dict):
            if not value:
                continue
            rendered = ", ".join(_md_code(f"{k}={v}") for k, v in value.items())
        else:
            rendered = _md_code(value)
        entries.append(f"- **{_md_escape(str(key))}:** {rendered}")
    return entries


def _md_outcome_block(outcome: Outcome) -> list[str]:
    lines = ["## Outcome", ""]
    rows: list[tuple[str, str]] = [("Verdict", f"**{_md_code(outcome.verdict)}**")]
    if outcome.confidence is not None:
        rows.append(("Confidence", f"{outcome.confidence * 100:.0f}%"))
    if outcome.summary:
        rows.append(("Summary", _md_cell(outcome.summary)))
    lines.append("| | |")
    lines.append("|---|---|")
    lines.extend(f"| {k} | {v} |" for k, v in rows)
    return lines


def _incoming_by_target(trace: DecisionTrace) -> dict[str, list[Edge]]:
    by_target: dict[str, list[Edge]] = {}
    for edge in trace.edges:
        by_target.setdefault(edge.target, []).append(edge)
    return by_target


def _steps_in_topological_order(trace: DecisionTrace) -> list[ReasoningStep]:
    """Topological order when possible; stable insertion order otherwise.

    Cycles or unreachable nodes fall back to insertion order for those
    specific steps so we never drop content from the output.
    """
    by_id = {s.id: s for s in trace.steps}
    outgoing: dict[str, list[str]] = {s.id: [] for s in trace.steps}
    indeg: dict[str, int] = {s.id: 0 for s in trace.steps}
    for edge in trace.edges:
        if edge.source in by_id and edge.target in by_id:
            outgoing[edge.source].append(edge.target)
            indeg[edge.target] += 1

    # Kahn's algorithm, preserving original step order as tie-breaker.
    insertion = {s.id: i for i, s in enumerate(trace.steps)}
    ready = sorted((sid for sid, n in indeg.items() if n == 0), key=insertion.get)
    order: list[str] = []
    seen: set[str] = set()
    while ready:
        sid = ready.pop(0)
        if sid in seen:
            continue
        seen.add(sid)
        order.append(sid)
        for child in outgoing[sid]:
            indeg[child] -= 1
            if indeg[child] == 0:
                # Insert sorted by original position.
                pos = 0
                while pos < len(ready) and insertion[ready[pos]] < insertion[child]:
                    pos += 1
                ready.insert(pos, child)
    # Append anything left (cycles / unreachable).
    for step in trace.steps:
        if step.id not in seen:
            order.append(step.id)
    return [by_id[sid] for sid in order]


# Escape only the CommonMark punctuation that meaningfully affects inline rendering
# outside code spans. We deliberately do NOT escape `.`, `-`, `+`, `(`, `)`, `!`,
# `#` — those create ugly output and rarely matter mid-paragraph.
_MD_ESCAPE_PATTERN = re.compile(r"([\\`*_\[\]<>|])")


def _md_escape(text: str) -> str:
    """Escape Markdown-active characters for use in plain text / headings / bold."""
    return _MD_ESCAPE_PATTERN.sub(r"\\\1", str(text))


def _md_code(value: object) -> str:
    """Render ``value`` as an inline code span, safe against embedded backticks."""
    raw = str(value)
    # Pick a fence long enough to contain the longest backtick run in the value.
    longest_run = 0
    current = 0
    for char in raw:
        if char == "`":
            current += 1
            longest_run = max(longest_run, current)
        else:
            current = 0
    fence = "`" * (longest_run + 1)
    pad = " " if raw.startswith("`") or raw.endswith("`") else ""
    return f"{fence}{pad}{raw}{pad}{fence}"


def _md_cell(text: str) -> str:
    """Escape pipes for table-cell context on top of normal inline escaping."""
    return _md_escape(text).replace("\n", " ")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def format_for(trace: DecisionTrace, fmt: str) -> str:
    """Dispatch helper — ``fmt`` in ``{"mermaid", "dot"/"graphviz", "markdown"/"md"}``."""
    fmt = fmt.lower()
    if fmt == "mermaid":
        return to_mermaid(trace)
    if fmt in ("dot", "graphviz"):
        return to_graphviz(trace)
    if fmt in ("markdown", "md"):
        return to_markdown(trace)
    raise ValueError(f"unknown export format: {fmt!r}")


__all__: Iterable[str] = ("to_mermaid", "to_graphviz", "to_markdown", "format_for")
