from __future__ import annotations

from theoria.models import (
    DecisionTrace,
    Outcome,
    ReasoningStep,
    StepKind,
    StepStatus,
)
from theoria.samples import build_samples
from theoria.stats import compute_stats


def _trace(
    trace_id: str, *, source="test", kind="custom", verdict=None, confidence=None,
    created_at="2026-04-23T12:00:00+00:00",
    rule_label=None, rule_status=StepStatus.TRIGGERED,
    concl_label=None, concl_status=StepStatus.OK,
) -> DecisionTrace:
    steps = [ReasoningStep(id="q", kind=StepKind.QUESTION, label="Q")]
    if rule_label:
        steps.append(ReasoningStep(id="r", kind=StepKind.RULE_CHECK,
                                   label=rule_label, status=rule_status))
    steps.append(ReasoningStep(id="c", kind=StepKind.CONCLUSION,
                               label=concl_label or "Done", status=concl_status))
    outcome = (
        Outcome(verdict=verdict, summary="", confidence=confidence)
        if verdict is not None else None
    )
    return DecisionTrace(
        id=trace_id, title=trace_id, question="?", source=source, kind=kind,
        root="q", steps=steps, outcome=outcome, created_at=created_at,
    )


def test_compute_stats_on_empty_input_is_safe() -> None:
    stats = compute_stats([])
    assert stats.total == 0
    assert stats.by_source == {}
    assert stats.mean_confidence is None
    assert stats.top_triggered_rules == []


def test_compute_stats_counts_by_source_kind_verdict() -> None:
    traces = [
        _trace("a", source="logos", kind="policy", verdict="block"),
        _trace("b", source="logos", kind="proof", verdict="proved"),
        _trace("c", source="praxis", kind="plan", verdict="plan-selected"),
    ]
    stats = compute_stats(traces)
    assert stats.total == 3
    assert stats.by_source == {"logos": 2, "praxis": 1}
    assert stats.by_kind == {"policy": 1, "proof": 1, "plan": 1}
    assert stats.by_verdict == {"block": 1, "proved": 1, "plan-selected": 1}


def test_compute_stats_mean_confidence_skips_none() -> None:
    traces = [
        _trace("a", verdict="x", confidence=1.0),
        _trace("b", verdict="x", confidence=0.5),
        _trace("c", verdict="x"),  # no confidence
    ]
    stats = compute_stats(traces)
    assert stats.mean_confidence == 0.75


def test_compute_stats_top_triggered_rules() -> None:
    traces = [
        _trace("a", rule_label="no_unauthorized_destruction"),
        _trace("b", rule_label="no_unauthorized_destruction"),
        _trace("c", rule_label="prefer_dry_run_first"),
    ]
    stats = compute_stats(traces, top_n=3)
    top = stats.top_triggered_rules
    assert top[0] == {"label": "no_unauthorized_destruction", "count": 2}
    assert top[1] == {"label": "prefer_dry_run_first", "count": 1}


def test_compute_stats_top_failed_conclusions() -> None:
    traces = [
        _trace("a", concl_label="Decision: BLOCK", concl_status=StepStatus.FAILED),
        _trace("b", concl_label="Decision: BLOCK", concl_status=StepStatus.FAILED),
        _trace("c", concl_label="Drift detected", concl_status=StepStatus.FAILED),
        _trace("d", concl_label="Pass", concl_status=StepStatus.OK),  # ignored
    ]
    stats = compute_stats(traces, top_n=2)
    labels = [entry["label"] for entry in stats.top_failed_conclusions]
    assert labels[0] == "Decision: BLOCK"
    assert "Drift detected" in labels


def test_compute_stats_by_day_is_chronological() -> None:
    traces = [
        _trace("a", verdict="x", created_at="2026-04-22T10:00:00+00:00"),
        _trace("b", verdict="x", created_at="2026-04-23T10:00:00+00:00"),
        _trace("c", verdict="x", created_at="2026-04-23T11:00:00+00:00"),
    ]
    stats = compute_stats(traces)
    assert list(stats.by_day.keys()) == ["2026-04-22", "2026-04-23"]
    assert stats.by_day["2026-04-23"] == 2


def test_compute_stats_handles_malformed_created_at() -> None:
    traces = [_trace("a", created_at="not-a-date")]
    stats = compute_stats(traces)
    # Malformed timestamps drop out of the day rollup but don't error.
    assert stats.by_day == {}
    assert stats.total == 1


def test_compute_stats_on_samples_has_expected_shape() -> None:
    stats = compute_stats(build_samples())
    assert stats.total == 4
    # All three distinct sources appear.
    assert set(stats.by_source) == {"logos", "praxis", "telos"}
    # The Logos sample has two triggered rule_checks — both should surface.
    labels = {entry["label"] for entry in stats.top_triggered_rules}
    assert "Rule: no_unauthorized_destruction" in labels
