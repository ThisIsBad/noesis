"""Techne core tests.

Covers SQLite + ChromaDB storage: store → retrieve → record-use.
Uses an ephemeral Chroma client + tmp-file SQLite so tests have no
filesystem side effects.
"""

from __future__ import annotations

import chromadb
import pytest
from noesis_schemas import ProofCertificate

from techne.core import TechneCore


@pytest.fixture
def core(tmp_path):
    return TechneCore(
        db_path=str(tmp_path / "techne.db"),
        _chroma_client=chromadb.EphemeralClient(),
    )


def _verified_cert() -> ProofCertificate:
    return ProofCertificate(
        claim_type="propositional",
        claim="strategy is correct",
        method="argument",
        verified=True,
        timestamp="2026-04-17T00:00:00+00:00",
    )


# ── store + retrieve ─────────────────────────────────────────────────────────


def test_store_and_retrieve_skill(core: TechneCore) -> None:
    core.store(
        "retry-on-failure",
        "Retry failed operations",
        "Call tool up to 3 times",
    )
    results = core.retrieve("retry")
    assert len(results) == 1
    assert results[0].name == "retry-on-failure"


def test_retrieve_uses_semantic_search_beyond_substring(core: TechneCore) -> None:
    """Chroma should surface conceptually-related skills the substring
    impl would miss. Pin a concrete example: 'retry' query hitting
    a skill described as 'attempt repeatedly'."""
    core.store(
        "attempt-again",
        "Attempt repeatedly after transient failures",
        "loop with backoff",
    )
    results = core.retrieve("retry on error", k=3)
    # Default all-MiniLM embedding places 'attempt repeatedly' /
    # 'retry on error' in the same neighbourhood. Assertion is
    # conservative: the skill surfaces within the top-3.
    assert any(r.name == "attempt-again" for r in results)


def test_verified_flag_from_certificate(core: TechneCore) -> None:
    skill = core.store(
        "proven-skill",
        "A verified strategy",
        "Do X then Y",
        certificate=_verified_cert(),
    )
    assert skill.verified


def test_get_returns_stored_skill(core: TechneCore) -> None:
    stored = core.store("s", "desc", "strat")
    got = core.get(stored.skill_id)
    assert got is not None
    assert got.skill_id == stored.skill_id


def test_get_unknown_returns_none(core: TechneCore) -> None:
    assert core.get("does-not-exist") is None


# ── verified_only filtering ─────────────────────────────────────────────────


def test_retrieve_verified_only_filters_unverified_matches(
    core: TechneCore,
) -> None:
    core.store("retry-loop", "Retry failed operations", "loop")
    assert core.retrieve("retry failed", verified_only=True) == []


def test_retrieve_verified_only_keeps_verified_matches(core: TechneCore) -> None:
    core.store(
        "proven-retry",
        "Retry failed operations",
        "loop",
        certificate=_verified_cert(),
    )
    results = core.retrieve("retry failed", verified_only=True)
    assert len(results) == 1
    assert results[0].name == "proven-retry"


def test_retrieve_verified_only_mixes_correctly(core: TechneCore) -> None:
    """Given both verified and unverified matches, verified_only only
    returns the verified subset."""
    core.store("unverified", "Retry failed operations", "loop")
    core.store(
        "verified",
        "Retry failed operations",
        "loop",
        certificate=_verified_cert(),
    )
    all_results = core.retrieve("retry")
    verified_only = core.retrieve("retry", verified_only=True)
    assert {s.name for s in all_results} == {"unverified", "verified"}
    assert {s.name for s in verified_only} == {"verified"}


# ── record_use ──────────────────────────────────────────────────────────────


def test_record_use_updates_success_rate(core: TechneCore) -> None:
    stored = core.store("test-skill", "test", "strategy")
    core.record_use(stored.skill_id, success=True)
    core.record_use(stored.skill_id, success=True)
    updated = core.record_use(stored.skill_id, success=False)
    assert abs(updated.success_rate - 2 / 3) < 0.01
    assert updated.use_count == 3


def test_record_use_on_unknown_skill_raises(core: TechneCore) -> None:
    with pytest.raises(KeyError):
        core.record_use("not-a-real-id", success=True)


def test_retrieve_ranks_by_success_rate(core: TechneCore) -> None:
    """Higher success-rate skill should rank above a lower-rate peer
    with equivalent relevance."""
    a = core.store("retry-a", "Retry failed operations", "loop")
    b = core.store("retry-b", "Retry failed operations", "loop")
    # A gets a perfect success record; B gets zero.
    core.record_use(a.skill_id, success=True)
    core.record_use(a.skill_id, success=True)
    core.record_use(b.skill_id, success=False)
    core.record_use(b.skill_id, success=False)

    ranked = core.retrieve("retry failed", k=2)
    assert [s.name for s in ranked] == ["retry-a", "retry-b"]


# ── persistence ─────────────────────────────────────────────────────────────


def test_persistence_survives_reopen(tmp_path) -> None:
    db_path = str(tmp_path / "persist.db")
    chroma_client = chromadb.EphemeralClient()

    c1 = TechneCore(db_path=db_path, _chroma_client=chroma_client)
    stored = c1.store("skill-persist", "persists across reopen", "strategy")

    c2 = TechneCore(db_path=db_path, _chroma_client=chroma_client)
    got = c2.get(stored.skill_id)
    assert got is not None
    assert got.name == "skill-persist"
