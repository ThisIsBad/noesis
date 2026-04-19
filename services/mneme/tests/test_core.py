import chromadb
import pytest
from noesis_schemas import MemoryType, ProofCertificate

from mneme.core import MnemeCore


@pytest.fixture
def core(tmp_path):
    # PersistentClient on tmp_path isolates the Chroma store per test.
    # EphemeralClient() uses a process-wide in-memory store — two fixtures
    # in the same session share it and pollute each other's assertions.
    return MnemeCore(
        db_path=str(tmp_path / "test.db"),
        _chroma_client=chromadb.PersistentClient(path=str(tmp_path / "chroma")),
    )


def test_store_and_retrieve(core):
    core.store("The sky is blue", MemoryType.SEMANTIC, confidence=0.9)
    results = core.retrieve("sky colour")
    assert len(results) == 1
    assert "blue" in results[0].content


def test_proven_flag_from_certificate(core):
    cert = ProofCertificate(
        claim_type="propositional",
        claim="Paris is capital of France",
        method="argument",
        verified=True,
        timestamp="2026-04-17T00:00:00+00:00",
    )
    mem = core.store(
        "Paris is the capital of France", MemoryType.SEMANTIC, certificate=cert
    )
    assert mem.proven
    assert core.list_proven() == [mem]


def test_forget(core):
    mem = core.store("temporary fact", MemoryType.EPISODIC)
    assert core.forget(mem.memory_id, "outdated")
    assert core.retrieve("temporary fact") == []


def test_forget_nonexistent_returns_false(core):
    assert not core.forget("does-not-exist", "reason")


def test_min_confidence_filter(core):
    core.store("low confidence fact", MemoryType.SEMANTIC, confidence=0.2)
    core.store("high confidence fact", MemoryType.SEMANTIC, confidence=0.9)
    results = core.retrieve("confidence fact", min_confidence=0.5)
    assert len(results) == 1
    assert results[0].confidence == 0.9


def test_retrieve_empty_collection(core):
    assert core.retrieve("anything") == []


def test_list_proven_empty(core):
    core.store("unproven belief", MemoryType.SEMANTIC)
    assert core.list_proven() == []


def test_persistence_across_instances(tmp_path):
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    db = str(tmp_path / "persist.db")
    c1 = MnemeCore(db_path=db, _chroma_client=client)
    mem = c1.store("persistent fact", MemoryType.SEMANTIC, confidence=0.8)

    # Same client + db_path: data survives re-instantiation
    c2 = MnemeCore(db_path=db, _chroma_client=client)
    results = c2.retrieve("persistent fact")
    assert any(r.memory_id == mem.memory_id for r in results)


def test_consolidate_merges_duplicate(core):
    core.store("The cat sat on the mat", MemoryType.SEMANTIC, confidence=0.6)
    core.store("A cat sat on a mat", MemoryType.SEMANTIC, confidence=0.9)
    merged = core.consolidate(similarity_threshold=0.5)
    assert merged >= 1
    # One entry should remain
    remaining = core.retrieve("cat mat", k=10)
    assert len(remaining) == 1
    assert remaining[0].confidence == 0.9
