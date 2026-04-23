from __future__ import annotations

from pathlib import Path

from theoria.models import DecisionTrace, ReasoningStep, StepKind
from theoria.samples import build_samples
from theoria.store import TraceStore


def _sample() -> DecisionTrace:
    step = ReasoningStep(id="q", kind=StepKind.QUESTION, label="Q")
    return DecisionTrace(
        id="t1",
        title="t1",
        question="Q?",
        source="test",
        kind="custom",
        root="q",
        steps=[step],
    )


def test_put_get_roundtrip() -> None:
    store = TraceStore()
    store.put(_sample())
    got = store.get("t1")
    assert got is not None
    assert got.id == "t1"


def test_list_is_most_recent_first() -> None:
    store = TraceStore()
    store.put(DecisionTrace(
        id="a", title="a", question="?", source="t", kind="c", root="q",
        steps=[ReasoningStep(id="q", kind=StepKind.QUESTION, label="a")],
    ))
    store.put(DecisionTrace(
        id="b", title="b", question="?", source="t", kind="c", root="q",
        steps=[ReasoningStep(id="q", kind=StepKind.QUESTION, label="b")],
    ))
    ordered = [t.id for t in store.list()]
    assert ordered == ["b", "a"]


def test_delete_removes_trace() -> None:
    store = TraceStore()
    store.put(_sample())
    assert store.delete("t1")
    assert not store.delete("t1")
    assert store.get("t1") is None


def test_put_many_accepts_samples() -> None:
    store = TraceStore()
    loaded = store.put_many(build_samples())
    assert loaded == len(build_samples())
    assert len(store) == loaded


def test_persistence_round_trip(tmp_path: Path) -> None:
    persist = tmp_path / "traces.jsonl"
    store = TraceStore(persist_path=persist)
    store.put(_sample())
    assert persist.exists()
    # New store reads existing jsonl.
    store2 = TraceStore(persist_path=persist)
    assert store2.get("t1") is not None


def test_clear_removes_file(tmp_path: Path) -> None:
    persist = tmp_path / "traces.jsonl"
    store = TraceStore(persist_path=persist)
    store.put(_sample())
    store.clear()
    assert not persist.exists()
    assert len(store) == 0
