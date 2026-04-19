"""Techne tracing wiring tests (no network — disabled mode only)."""
import techne.tracing as tracing_mod
from techne.tracing import get_tracer, reset_tracer_for_tests


def test_disabled_when_no_kairos_url(monkeypatch):
    monkeypatch.delenv("KAIROS_URL", raising=False)
    monkeypatch.delenv("TECHNE_TRACE_ENABLED", raising=False)
    reset_tracer_for_tests()
    assert get_tracer().disabled is True


def test_disabled_when_flag_off(monkeypatch):
    monkeypatch.setenv("KAIROS_URL", "http://kairos.local")
    monkeypatch.setenv("TECHNE_TRACE_ENABLED", "0")
    reset_tracer_for_tests()
    assert get_tracer().disabled is True


def test_enabled_with_url(monkeypatch):
    monkeypatch.setenv("KAIROS_URL", "http://kairos.local")
    monkeypatch.setenv("TECHNE_TRACE_ENABLED", "1")
    reset_tracer_for_tests()
    assert get_tracer().disabled is False


def test_tracer_is_cached(monkeypatch):
    monkeypatch.delenv("KAIROS_URL", raising=False)
    reset_tracer_for_tests()
    assert get_tracer() is get_tracer()


def test_span_runs_when_disabled(monkeypatch):
    monkeypatch.delenv("KAIROS_URL", raising=False)
    reset_tracer_for_tests()
    tracer = get_tracer()
    with tracer.span("store_skill") as trace_id:
        assert isinstance(trace_id, str) and trace_id


def test_tracing_module_uses_techne_service_name():
    assert tracing_mod._SERVICE_NAME == "techne"


def test_reset_drops_cache(monkeypatch):
    monkeypatch.delenv("KAIROS_URL", raising=False)
    reset_tracer_for_tests()
    first = get_tracer()
    reset_tracer_for_tests()
    second = get_tracer()
    assert first is not second
