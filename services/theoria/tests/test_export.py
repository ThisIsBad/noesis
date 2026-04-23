from __future__ import annotations

import pytest

from theoria.export import format_for, to_graphviz, to_markdown, to_mermaid
from theoria.samples import build_samples


@pytest.fixture(scope="module")
def samples():
    return build_samples()


def test_mermaid_has_header_and_all_nodes(samples) -> None:
    trace = samples[0]  # logos policy block
    out = to_mermaid(trace)
    assert out.startswith("%%")
    assert "flowchart TD" in out
    for step in trace.steps:
        # every node id must appear (sanitized form still contains most chars)
        assert step.id.replace(".", "_") in out or step.id in out


def test_mermaid_emits_class_definitions(samples) -> None:
    out = to_mermaid(samples[0])
    for cls in ("ok", "failed", "triggered", "info"):
        assert f"classDef {cls}" in out


def test_mermaid_escapes_pipe_and_quote() -> None:
    from theoria.models import DecisionTrace, ReasoningStep, StepKind
    trace = DecisionTrace(
        id="t", title="t", question="?", source="s", kind="k", root="a",
        steps=[ReasoningStep(id="a", kind=StepKind.NOTE, label='Hello | "World"')],
    )
    out = to_mermaid(trace)
    assert "&#124;" in out   # pipe escaped
    assert "&quot;" in out   # quote escaped
    assert "|" not in _label_body(out)  # raw pipe does not appear inside the label


def test_graphviz_is_valid_looking_dot(samples) -> None:
    out = to_graphviz(samples[1])   # praxis plan
    assert out.startswith("//")
    assert "digraph Trace" in out
    assert "rankdir=TB" in out
    assert out.rstrip().endswith("}")


def test_graphviz_escapes_quote_in_label() -> None:
    from theoria.models import DecisionTrace, ReasoningStep, StepKind
    trace = DecisionTrace(
        id="t", title="t", question="?", source="s", kind="k", root="a",
        steps=[ReasoningStep(id="a", kind=StepKind.NOTE, label='Say "hi"')],
    )
    out = to_graphviz(trace)
    assert '\\"' in out     # escaped double quote


def test_format_for_dispatch(samples) -> None:
    assert format_for(samples[0], "mermaid").startswith("%%")
    assert format_for(samples[0], "dot").startswith("//")
    assert format_for(samples[0], "graphviz").startswith("//")
    assert format_for(samples[0], "markdown").startswith("# ")
    assert format_for(samples[0], "md").startswith("# ")
    with pytest.raises(ValueError):
        format_for(samples[0], "pdf")


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def test_markdown_has_header_and_metadata_table(samples) -> None:
    trace = samples[0]  # logos policy block
    out = to_markdown(trace)
    first_line = out.splitlines()[0]
    assert first_line.startswith("# ")
    assert "| Field | Value |" in out
    assert "| Source |" in out
    assert "`logos`" in out


def test_markdown_embeds_mermaid_fence(samples) -> None:
    out = to_markdown(samples[0])
    assert "```mermaid" in out
    assert "flowchart TD" in out
    # Ensure the fence is correctly closed.
    mermaid_opens = out.count("```mermaid")
    fence_closes = out.count("```")
    # One opening ```mermaid + one closing ``` = 2 total triple-backticks.
    assert mermaid_opens == 1
    assert fence_closes >= 2


def test_markdown_can_disable_mermaid_embed(samples) -> None:
    out = to_markdown(samples[0], embed_mermaid=False)
    assert "```mermaid" not in out
    # But steps section still rendered.
    assert "## Steps" in out


def test_markdown_lists_every_step_in_topological_order() -> None:
    from theoria.models import DecisionTrace, Edge, EdgeRelation, ReasoningStep, StepKind
    trace = DecisionTrace(
        id="t", title="t", question="?", source="s", kind="k", root="q",
        steps=[
            ReasoningStep(id="q", kind=StepKind.QUESTION, label="Q"),
            ReasoningStep(id="c", kind=StepKind.CONCLUSION, label="C"),
            ReasoningStep(id="m", kind=StepKind.INFERENCE, label="M"),
        ],
        edges=[
            Edge("q", "m", EdgeRelation.REQUIRES),
            Edge("m", "c", EdgeRelation.YIELDS),
        ],
    )
    out = to_markdown(trace, embed_mermaid=False)
    pos_q = out.index("### `q`")
    pos_m = out.index("### `m`")
    pos_c = out.index("### `c`")
    assert pos_q < pos_m < pos_c


def test_markdown_shows_incoming_edges_inline() -> None:
    from theoria.models import DecisionTrace, Edge, EdgeRelation, ReasoningStep, StepKind
    trace = DecisionTrace(
        id="t", title="t", question="?", source="s", kind="k", root="a",
        steps=[
            ReasoningStep(id="a", kind=StepKind.QUESTION, label="A"),
            ReasoningStep(id="b", kind=StepKind.CONCLUSION, label="B"),
        ],
        edges=[Edge("a", "b", EdgeRelation.IMPLIES, "because")],
    )
    out = to_markdown(trace, embed_mermaid=False)
    # The B step should surface its incoming edge from A.
    b_section = out[out.index("### `b`"):]
    assert "*From:*" in b_section
    assert "implies" in b_section
    assert "because" in b_section


def test_markdown_escapes_special_characters() -> None:
    from theoria.models import DecisionTrace, ReasoningStep, StepKind
    trace = DecisionTrace(
        id="t", title="Title with |pipe| and [bracket]", question="?",
        source="s", kind="k", root="a",
        steps=[ReasoningStep(id="a", kind=StepKind.NOTE, label="has_*underscore*_and_`backtick`")],
    )
    out = to_markdown(trace, embed_mermaid=False)
    # Pipe must be escaped inside the header so tables aren't corrupted.
    first_line = out.splitlines()[0]
    assert "\\|pipe\\|" in first_line
    assert "\\[bracket\\]" in first_line
    # Asterisks and backticks inside labels are escaped.
    assert "\\*underscore\\*" in out
    assert "\\`backtick\\`" in out


def test_markdown_includes_outcome_section_when_present(samples) -> None:
    out = to_markdown(samples[0])
    assert "## Outcome" in out
    # Outcome table references the verdict value.
    assert "**`block`**" in out or "block" in out


def test_markdown_topological_order_handles_cycles_gracefully() -> None:
    from theoria.models import DecisionTrace, Edge, EdgeRelation, ReasoningStep, StepKind
    # Build a cycle b → c → b under a root a.
    trace = DecisionTrace(
        id="t", title="t", question="?", source="s", kind="k", root="a",
        steps=[
            ReasoningStep(id="a", kind=StepKind.QUESTION, label="A"),
            ReasoningStep(id="b", kind=StepKind.INFERENCE, label="B"),
            ReasoningStep(id="c", kind=StepKind.INFERENCE, label="C"),
        ],
        edges=[
            Edge("a", "b", EdgeRelation.REQUIRES),
            Edge("b", "c", EdgeRelation.SUPPORTS),
            Edge("c", "b", EdgeRelation.SUPPORTS),
        ],
    )
    out = to_markdown(trace, embed_mermaid=False)
    # All three step headers appear — fallback path keeps the cycle nodes.
    assert "### `a`" in out
    assert "### `b`" in out
    assert "### `c`" in out


def _label_body(mermaid: str) -> str:
    # Strip class-def lines which intentionally contain pipes in some themes.
    return "\n".join(line for line in mermaid.splitlines() if not line.strip().startswith("classDef"))
