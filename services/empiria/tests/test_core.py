"""Empiria core tests.

Covers SQLite + ChromaDB storage: record → retrieve → successful_patterns.
Uses an ephemeral Chroma client + tmp-file SQLite so tests have no
filesystem side effects.
"""
from __future__ import annotations

import chromadb
import pytest

from empiria.core import EmpiriaCore


@pytest.fixture
def core(tmp_path):
    return EmpiriaCore(
        db_path=str(tmp_path / "empiria.db"),
        _chroma_client=chromadb.EphemeralClient(),
    )


# ── record + retrieve ────────────────────────────────────────────────────────


def test_record_and_retrieve(core: EmpiriaCore) -> None:
    core.record(
        context="deploy service",
        action_taken="restart container",
        outcome="service recovered",
        success=True,
        lesson_text="Restart fixes transient deploy failures",
        domain="devops",
    )
    results = core.retrieve("deploy", domain="devops")
    assert len(results) == 1
    assert results[0].success


def test_retrieve_returns_empty_when_no_lessons(core: EmpiriaCore) -> None:
    assert core.retrieve("anything") == []


def test_retrieve_sorts_by_confidence(core: EmpiriaCore) -> None:
    """Two equally-relevant lessons re-sort with the higher-confidence first."""
    low = core.record(
        "deploy", "action1", "ok", True, "low-belief lesson", confidence=0.3,
    )
    high = core.record(
        "deploy", "action2", "ok", True, "high-belief lesson", confidence=0.9,
    )
    results = core.retrieve("deploy")
    # high confidence wins on ties.
    assert results[0].lesson_id == high.lesson_id
    assert results[-1].lesson_id == low.lesson_id


def test_retrieve_semantic_beyond_substring(core: EmpiriaCore) -> None:
    """Embedding match should pull a semantically-close lesson, not just a substring."""
    core.record(
        context="restart the application after a crash",
        action_taken="systemctl restart app",
        outcome="back up",
        success=True,
        lesson_text="reboot the service to clear the wedged state",
    )
    # Query uses different lexical form than the stored context.
    results = core.retrieve("how do I recover from a crash?")
    assert len(results) == 1


def test_retrieve_filters_by_domain(core: EmpiriaCore) -> None:
    core.record("ctx", "a", "ok", True, "devops lesson", domain="devops")
    core.record("ctx", "b", "ok", True, "ml lesson", domain="ml")
    in_devops = core.retrieve("ctx", domain="devops")
    in_ml = core.retrieve("ctx", domain="ml")
    assert len(in_devops) == 1 and in_devops[0].domain == "devops"
    assert len(in_ml) == 1 and in_ml[0].domain == "ml"


def test_retrieve_caps_at_k(core: EmpiriaCore) -> None:
    for i in range(7):
        core.record("ctx", f"a{i}", "ok", True, f"lesson {i}")
    assert len(core.retrieve("ctx", k=3)) == 3


# ── successful_patterns ──────────────────────────────────────────────────────


def test_successful_patterns_filters_failures(core: EmpiriaCore) -> None:
    core.record("ctx", "a", "ok", True, "worked", domain="x")
    core.record("ctx", "b", "fail", False, "failed", domain="x")
    patterns = core.successful_patterns(domain="x")
    assert len(patterns) == 1
    assert patterns[0].success
    assert patterns[0].lesson_text == "worked"


def test_successful_patterns_no_domain_returns_all_wins(core: EmpiriaCore) -> None:
    core.record("ctx", "a", "ok", True, "win-1", domain="x")
    core.record("ctx", "b", "ok", True, "win-2", domain="y")
    core.record("ctx", "c", "no", False, "loss", domain="x")
    wins = core.successful_patterns()
    assert {lesson.lesson_text for lesson in wins} == {"win-1", "win-2"}


# ── get + persistence ────────────────────────────────────────────────────────


def test_get_returns_stored_lesson(core: EmpiriaCore) -> None:
    stored = core.record("ctx", "a", "ok", True, "the lesson")
    fetched = core.get(stored.lesson_id)
    assert fetched is not None
    assert fetched.lesson_id == stored.lesson_id
    assert fetched.lesson_text == "the lesson"


def test_get_returns_none_when_missing(core: EmpiriaCore) -> None:
    assert core.get("does-not-exist") is None


def test_lesson_persists_across_reopen(tmp_path) -> None:
    """SQLite + a *persistent* Chroma should survive a process restart."""
    db_path = str(tmp_path / "empiria.db")
    chroma_path = str(tmp_path / "empiria_chroma")
    first = EmpiriaCore(db_path=db_path, chroma_path=chroma_path)
    stored = first.record(
        "post-mortem",
        "wrote runbook",
        "team unblocked",
        True,
        "always document the recovery sequence",
    )
    del first

    second = EmpiriaCore(db_path=db_path, chroma_path=chroma_path)
    fetched = second.get(stored.lesson_id)
    assert fetched is not None
    assert fetched.lesson_text == "always document the recovery sequence"
    # And retrieval still finds it post-reopen.
    results = second.retrieve("how do we recover?")
    assert any(r.lesson_id == stored.lesson_id for r in results)
