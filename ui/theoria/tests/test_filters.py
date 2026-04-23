from __future__ import annotations

from datetime import datetime, timezone

from theoria.filters import TraceFilter, apply_filter, filter_from_query
from theoria.models import DecisionTrace, Outcome, ReasoningStep, StepKind


def _trace(**kwargs) -> DecisionTrace:
    defaults = dict(
        id="t", title="Title", question="Question?", source="logos", kind="policy", root="q",
        steps=[ReasoningStep(id="q", kind=StepKind.QUESTION, label="Q")],
        outcome=Outcome(verdict="allow", summary="ok"),
        tags=["a", "b"],
        created_at="2026-04-23T12:00:00+00:00",
    )
    defaults.update(kwargs)
    return DecisionTrace(**defaults)


def test_empty_filter_matches_all() -> None:
    t = _trace()
    assert TraceFilter().matches(t) is True


def test_source_filter_is_exact() -> None:
    t = _trace(source="logos")
    assert TraceFilter(source="logos").matches(t)
    assert not TraceFilter(source="praxis").matches(t)


def test_kind_and_verdict_filters() -> None:
    t = _trace(kind="policy", outcome=Outcome(verdict="block", summary=""))
    assert TraceFilter(kind="policy", verdict="block").matches(t)
    assert not TraceFilter(kind="policy", verdict="allow").matches(t)


def test_verdict_filter_rejects_traces_without_outcome() -> None:
    t = _trace(outcome=None)
    assert not TraceFilter(verdict="allow").matches(t)


def test_tag_filter_matches_on_any_overlap() -> None:
    t = _trace(tags=["a", "b"])
    assert TraceFilter(tags=("b", "c")).matches(t)
    assert not TraceFilter(tags=("x", "y")).matches(t)


def test_text_filter_matches_title_question_labels() -> None:
    t = _trace(
        title="Refactor auth",
        question="Is this allowed?",
        steps=[
            ReasoningStep(id="q", kind=StepKind.QUESTION, label="Q"),
            ReasoningStep(id="e", kind=StepKind.EVIDENCE, label="detecting DATABASE drift"),
        ],
    )
    assert TraceFilter(text="database").matches(t)
    assert TraceFilter(text="auth").matches(t)
    assert TraceFilter(text="allowed").matches(t)
    assert not TraceFilter(text="kubernetes").matches(t)


def test_since_and_until_filters() -> None:
    t = _trace(created_at="2026-04-23T12:00:00+00:00")
    before = datetime(2026, 4, 23, 11, 0, tzinfo=timezone.utc)
    after = datetime(2026, 4, 23, 13, 0, tzinfo=timezone.utc)

    assert TraceFilter(since=before, until=after).matches(t)
    assert not TraceFilter(since=after).matches(t)
    assert not TraceFilter(until=before).matches(t)


def test_apply_filter_respects_limit() -> None:
    traces = [_trace(id=f"t{i}") for i in range(10)]
    out = apply_filter(traces, None, limit=3)
    assert [t.id for t in out] == ["t0", "t1", "t2"]


def test_filter_from_query_parses_all_fields() -> None:
    query = {
        "source": ["logos"],
        "kind": ["policy"],
        "verdict": ["block"],
        "tag": ["a", "b"],
        "q": ["rename"],
        "since": ["2026-04-23T00:00:00Z"],
        "until": ["2026-04-24T00:00:00Z"],
        "limit": ["5"],
    }
    flt, limit = filter_from_query(query)
    assert flt.source == "logos"
    assert flt.kind == "policy"
    assert flt.verdict == "block"
    assert set(flt.tags) == {"a", "b"}
    assert flt.text == "rename"
    assert flt.since == datetime(2026, 4, 23, tzinfo=timezone.utc)
    assert flt.until == datetime(2026, 4, 24, tzinfo=timezone.utc)
    assert limit == 5


def test_filter_from_query_handles_comma_separated_tags() -> None:
    flt, _ = filter_from_query({"tag": ["policy,block"]})
    assert set(flt.tags) == {"policy", "block"}


def test_filter_from_query_ignores_malformed_timestamps() -> None:
    flt, _ = filter_from_query({"since": ["not-a-date"]})
    assert flt.since is None
