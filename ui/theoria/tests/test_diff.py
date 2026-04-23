from __future__ import annotations

import copy

from theoria.diff import diff_to_markdown, diff_to_mermaid, diff_traces
from theoria.models import (
    DecisionTrace,
    Edge,
    EdgeRelation,
    Outcome,
    ReasoningStep,
    StepKind,
    StepStatus,
)
from theoria.samples import build_samples


def _sample_trace() -> DecisionTrace:
    return DecisionTrace(
        id="t",
        title="base",
        question="Q?",
        source="test",
        kind="custom",
        root="q",
        steps=[
            ReasoningStep(id="q", kind=StepKind.QUESTION, label="Q"),
            ReasoningStep(id="a", kind=StepKind.OBSERVATION, label="A", status=StepStatus.OK),
            ReasoningStep(id="c", kind=StepKind.CONCLUSION, label="C", status=StepStatus.OK),
        ],
        edges=[
            Edge("q", "a", EdgeRelation.CONSIDERS),
            Edge("a", "c", EdgeRelation.IMPLIES),
        ],
        outcome=Outcome(verdict="allow", summary="ok"),
    )


def test_diff_identical_traces_is_empty() -> None:
    base = _sample_trace()
    diff = diff_traces(base, copy.deepcopy(base))
    assert diff.is_empty
    assert diff.added_steps == []
    assert diff.removed_steps == []
    assert diff.changed_steps == []
    assert diff.outcome_change is None


def test_diff_detects_added_and_removed_steps() -> None:
    base = _sample_trace()
    new = _sample_trace()
    new.steps.append(ReasoningStep(id="x", kind=StepKind.EVIDENCE, label="extra"))
    new.edges.append(Edge("a", "x", EdgeRelation.SUPPORTS))

    diff = diff_traces(base, new)
    assert [s.id for s in diff.added_steps] == ["x"]
    assert diff.removed_steps == []
    assert len(diff.added_edges) == 1
    assert (diff.added_edges[0].source, diff.added_edges[0].target) == ("a", "x")


def test_diff_detects_removed_steps_and_edges() -> None:
    base = _sample_trace()
    new = _sample_trace()
    new.steps = [s for s in new.steps if s.id != "a"]
    new.edges = [e for e in new.edges if "a" not in (e.source, e.target)]
    # Add a direct edge so the graph still validates.
    new.edges.append(Edge("q", "c", EdgeRelation.IMPLIES))

    diff = diff_traces(base, new)
    assert [s.id for s in diff.removed_steps] == ["a"]
    removed_endpoints = {(e.source, e.target) for e in diff.removed_edges}
    assert ("q", "a") in removed_endpoints
    assert ("a", "c") in removed_endpoints


def test_diff_detects_changed_step_fields() -> None:
    base = _sample_trace()
    new = _sample_trace()
    target = next(s for s in new.steps if s.id == "c")
    target.label = "C prime"
    target.status = StepStatus.FAILED

    diff = diff_traces(base, new)
    assert len(diff.changed_steps) == 1
    change = diff.changed_steps[0]
    assert change.id == "c"
    assert "label" in change.field_changes
    assert change.field_changes["label"] == ("C", "C prime")
    assert change.field_changes["status"] == ("ok", "failed")


def test_diff_detects_outcome_change() -> None:
    base = _sample_trace()
    new = _sample_trace()
    assert new.outcome is not None
    new.outcome.verdict = "block"

    diff = diff_traces(base, new)
    assert diff.outcome_change is not None
    old, new_payload = diff.outcome_change
    assert old is not None and new_payload is not None
    assert old["verdict"] == "allow"
    assert new_payload["verdict"] == "block"


def test_diff_to_dict_round_trip_shape() -> None:
    base = _sample_trace()
    new = _sample_trace()
    new.steps.append(ReasoningStep(id="x", kind=StepKind.NOTE, label="x"))
    diff = diff_traces(base, new)
    payload = diff.to_dict()
    assert payload["a_id"] == base.id
    assert payload["b_id"] == new.id
    assert [s["id"] for s in payload["added_steps"]] == ["x"]
    assert payload["is_empty"] is False


def test_diff_markdown_includes_summary_and_sections() -> None:
    base = _sample_trace()
    new = _sample_trace()
    new.steps.append(ReasoningStep(id="x", kind=StepKind.EVIDENCE, label="new evidence"))
    new.edges.append(Edge("a", "x", EdgeRelation.SUPPORTS))
    target = next(s for s in new.steps if s.id == "c")
    target.status = StepStatus.FAILED
    assert new.outcome is not None
    new.outcome.verdict = "block"

    diff = diff_traces(base, new)
    md = diff_to_markdown(diff)
    assert md.startswith("# Trace diff")
    assert "## Added steps" in md
    assert "new evidence" in md
    assert "## Changed steps" in md
    assert "## Added edges" in md
    assert "## Outcome change" in md
    assert "```mermaid" in md


def test_diff_markdown_when_empty_says_so() -> None:
    base = _sample_trace()
    diff = diff_traces(base, copy.deepcopy(base))
    md = diff_to_markdown(diff)
    assert "No structural changes" in md


def test_diff_mermaid_classes_for_each_change_type() -> None:
    base = _sample_trace()
    new = _sample_trace()
    new.steps.append(ReasoningStep(id="x", kind=StepKind.NOTE, label="x"))
    new.edges.append(Edge("a", "x", EdgeRelation.SUPPORTS))
    target = next(s for s in new.steps if s.id == "a")
    target.status = StepStatus.TRIGGERED

    diff = diff_traces(base, new)
    mm = diff_to_mermaid(diff)
    assert "flowchart TD" in mm
    assert "class " in mm and " added" in mm
    assert " changed" in mm
    assert "classDef added" in mm
    assert "classDef removed" in mm
    assert "classDef changed" in mm


def test_diff_samples_real_world_like() -> None:
    # Using the built-in samples as a realistic smoke test.
    samples = build_samples()
    diff = diff_traces(samples[0], samples[1])
    # Different sources + different step IDs — expect lots of churn.
    assert len(diff.added_steps) > 0
    assert len(diff.removed_steps) > 0
    # Should render both Markdown and Mermaid without error.
    assert diff_to_markdown(diff).startswith("# Trace diff")
    assert diff_to_mermaid(diff).startswith("%% Trace diff")
