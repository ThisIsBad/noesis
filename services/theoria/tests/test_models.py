from __future__ import annotations

import pytest

from theoria.models import (
    DecisionTrace,
    Edge,
    EdgeRelation,
    Outcome,
    ReasoningStep,
    StepKind,
    StepStatus,
    trace_from_steps,
)


def _minimal_trace() -> DecisionTrace:
    root = ReasoningStep(id="q", kind=StepKind.QUESTION, label="Should we?")
    concl = ReasoningStep(id="c", kind=StepKind.CONCLUSION, label="Yes", status=StepStatus.OK)
    return trace_from_steps(
        trace_id="t1",
        title="Trivial",
        question="Should we?",
        source="test",
        kind="custom",
        steps=[root, concl],
        edges=[Edge("q", "c", EdgeRelation.YIELDS)],
        outcome=Outcome(verdict="allow", summary="yes", confidence=1.0),
        tags=("demo",),
    )


def test_trace_round_trip_preserves_structure() -> None:
    original = _minimal_trace()
    payload = original.to_dict()
    restored = DecisionTrace.from_dict(payload)

    assert restored.id == "t1"
    assert restored.root == "q"
    assert len(restored.steps) == 2
    assert [s.id for s in restored.steps] == ["q", "c"]
    assert restored.edges[0].relation is EdgeRelation.YIELDS
    assert restored.outcome is not None
    assert restored.outcome.verdict == "allow"


def test_trace_validate_rejects_dangling_edges() -> None:
    trace = _minimal_trace()
    trace.edges.append(Edge("q", "does-not-exist", EdgeRelation.SUPPORTS))
    with pytest.raises(ValueError, match="Edge target"):
        trace.validate()


def test_trace_validate_rejects_duplicate_step_ids() -> None:
    root = ReasoningStep(id="q", kind=StepKind.QUESTION, label="Q")
    dupe = ReasoningStep(id="q", kind=StepKind.NOTE, label="dup")
    trace = DecisionTrace(
        id="x",
        title="x",
        question="?",
        source="t",
        kind="custom",
        root="q",
        steps=[root, dupe],
    )
    with pytest.raises(ValueError, match="Duplicate step IDs"):
        trace.validate()


def test_trace_validate_rejects_unknown_root() -> None:
    step = ReasoningStep(id="a", kind=StepKind.NOTE, label="a")
    trace = DecisionTrace(
        id="x",
        title="x",
        question="?",
        source="t",
        kind="custom",
        root="missing",
        steps=[step],
    )
    with pytest.raises(ValueError, match="Root id"):
        trace.validate()


def test_step_from_dict_round_trip() -> None:
    step = ReasoningStep(
        id="s",
        kind=StepKind.INFERENCE,
        label="infer",
        detail="because",
        status=StepStatus.TRIGGERED,
        confidence=0.62,
        source_ref="file.py:10",
        meta={"k": "v"},
    )
    restored = ReasoningStep.from_dict(step.to_dict())
    assert restored == step


def test_step_from_dict_requires_fields() -> None:
    with pytest.raises(ValueError):
        ReasoningStep.from_dict({"id": "x", "kind": "note"})  # missing label


def test_trace_from_steps_requires_non_empty() -> None:
    with pytest.raises(ValueError):
        trace_from_steps(
            trace_id="t",
            title="t",
            question="?",
            source="s",
            kind="k",
            steps=[],
            edges=[],
        )
