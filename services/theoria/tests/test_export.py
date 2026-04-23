from __future__ import annotations

import pytest

from theoria.export import format_for, to_graphviz, to_mermaid
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
    with pytest.raises(ValueError):
        format_for(samples[0], "pdf")


def _label_body(mermaid: str) -> str:
    # Strip class-def lines which intentionally contain pipes in some themes.
    return "\n".join(line for line in mermaid.splitlines() if not line.strip().startswith("classDef"))
