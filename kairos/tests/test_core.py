from datetime import datetime, timedelta

from kairos.core import KairosCore


def test_record_and_retrieve_span():
    core = KairosCore()
    span = core.record_span(
        service="mneme",
        operation="store_memory",
        trace_id="trace-1",
        duration_ms=42.0,
        success=True,
    )
    assert span.service == "mneme"
    assert span.duration_ms == 42.0

    trace = core.get_trace("trace-1")
    assert len(trace) == 1
    assert trace[0].span_id == span.span_id


def test_get_recent_limit():
    core = KairosCore()
    for i in range(10):
        core.record_span(
            service="praxis",
            operation="decompose_goal",
            trace_id=f"t-{i}",
        )
    assert len(core.get_recent(limit=5)) == 5


def test_trace_isolation():
    core = KairosCore()
    core.record_span(service="a", operation="op", trace_id="trace-x")
    core.record_span(service="b", operation="op", trace_id="trace-y")
    assert len(core.get_trace("trace-x")) == 1
    assert len(core.get_trace("trace-y")) == 1


def _seed(core: KairosCore) -> None:
    core.record_span(
        service="mneme", operation="store_memory", trace_id="t1",
        duration_ms=5.0, success=True,
    )
    core.record_span(
        service="praxis", operation="decompose_goal", trace_id="t1",
        duration_ms=150.0, success=True,
    )
    core.record_span(
        service="mneme", operation="retrieve_memory", trace_id="t2",
        duration_ms=12.0, success=False,
    )
    core.record_span(
        service="telos", operation="check_alignment", trace_id="t2",
        duration_ms=2.0, success=True,
    )


def test_query_spans_by_service():
    core = KairosCore()
    _seed(core)
    result = core.query_spans(service="mneme")
    assert [s.operation for s in result] == ["store_memory", "retrieve_memory"]


def test_query_spans_by_operation():
    core = KairosCore()
    _seed(core)
    result = core.query_spans(operation="decompose_goal")
    assert len(result) == 1
    assert result[0].service == "praxis"


def test_query_spans_by_trace_id_matches_get_trace():
    core = KairosCore()
    _seed(core)
    query_result = core.query_spans(trace_id="t1")
    trace_result = core.get_trace("t1")
    assert [s.span_id for s in query_result] == [s.span_id for s in trace_result]


def test_query_spans_by_success_flag():
    core = KairosCore()
    _seed(core)
    failures = core.query_spans(success=False)
    assert len(failures) == 1
    assert failures[0].operation == "retrieve_memory"


def test_query_spans_min_duration_ms_excludes_fast_spans():
    core = KairosCore()
    _seed(core)
    slow = core.query_spans(min_duration_ms=10.0)
    assert {s.operation for s in slow} == {"decompose_goal", "retrieve_memory"}


def test_query_spans_since_filter():
    core = KairosCore()
    # Seed an old span by reaching into the store directly after record.
    old = core.record_span(service="svc", operation="old_op", trace_id="t-old")
    old.ended_at = datetime.utcnow() - timedelta(hours=1)
    core.record_span(service="svc", operation="new_op", trace_id="t-new")
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    recent = core.query_spans(since=cutoff)
    assert [s.operation for s in recent] == ["new_op"]


def test_query_spans_combines_filters_with_and():
    core = KairosCore()
    _seed(core)
    result = core.query_spans(service="mneme", success=True)
    assert len(result) == 1
    assert result[0].operation == "store_memory"


def test_query_spans_respects_limit():
    core = KairosCore()
    for i in range(20):
        core.record_span(service="s", operation="op", trace_id=f"t{i}")
    result = core.query_spans(service="s", limit=5)
    assert len(result) == 5
    # Limit returns the *tail* (most recent) matches.
    assert result[-1].trace_id == "t19"
