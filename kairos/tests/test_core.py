from kairos.core import KairosCore


def test_record_and_retrieve_span():
    core = KairosCore()
    span = core.record_span(service="mneme", operation="store_memory", trace_id="trace-1", duration_ms=42.0, success=True)
    assert span.service == "mneme"
    assert span.duration_ms == 42.0

    trace = core.get_trace("trace-1")
    assert len(trace) == 1
    assert trace[0].span_id == span.span_id


def test_get_recent_limit():
    core = KairosCore()
    for i in range(10):
        core.record_span(service="praxis", operation="decompose_goal", trace_id=f"t-{i}")
    assert len(core.get_recent(limit=5)) == 5


def test_trace_isolation():
    core = KairosCore()
    core.record_span(service="a", operation="op", trace_id="trace-x")
    core.record_span(service="b", operation="op", trace_id="trace-y")
    assert len(core.get_trace("trace-x")) == 1
    assert len(core.get_trace("trace-y")) == 1
