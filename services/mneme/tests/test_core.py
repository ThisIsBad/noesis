from mneme.core import MnemeCore
from noesis_schemas import MemoryType, ProofCertificate


def test_store_and_retrieve():
    core = MnemeCore()
    core.store("The sky is blue", MemoryType.SEMANTIC, confidence=0.9)
    results = core.retrieve("sky")
    assert len(results) == 1
    assert "blue" in results[0].content


def test_proven_flag_from_certificate():
    core = MnemeCore()
    cert = ProofCertificate(claim="Paris is capital of France", proven=True, method="argument")
    mem = core.store("Paris is the capital of France", MemoryType.SEMANTIC, certificate=cert)
    assert mem.proven
    assert core.list_proven() == [mem]


def test_forget():
    core = MnemeCore()
    mem = core.store("temporary fact", MemoryType.EPISODIC)
    assert core.forget(mem.memory_id, "outdated")
    assert core.retrieve("temporary fact") == []


def test_min_confidence_filter():
    core = MnemeCore()
    core.store("low confidence fact", MemoryType.SEMANTIC, confidence=0.2)
    core.store("high confidence fact", MemoryType.SEMANTIC, confidence=0.9)
    results = core.retrieve("confidence fact", min_confidence=0.5)
    assert len(results) == 1
    assert results[0].confidence == 0.9
