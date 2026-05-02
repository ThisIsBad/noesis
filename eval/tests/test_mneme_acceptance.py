"""Mneme acceptance benchmarks.

Targets (from docs/ROADMAP.md):
  * Recall@10 ≥ 0.80 on the 500 query/expected corpus
  * Consolidation reduces duplicates ≥ 40% with Recall loss ≤ 5pp
  * p99 retrieve_memory latency ≤ 200ms at 100k entries

The 100k-entry latency run is opt-in via MNEME_BENCH_LATENCY_N because
populating ChromaDB at that scale takes minutes; CI runs a smaller N to
catch regressions in the instrumentation itself.
"""

from __future__ import annotations

import os
import time

import pytest

chromadb = pytest.importorskip("chromadb")
pytest.importorskip("mneme")

from mneme.core import MnemeCore  # noqa: E402
from noesis_schemas import MemoryType  # noqa: E402

from noesis_eval.mneme_bench import (  # noqa: E402
    BenchPair,
    generate_pairs,
    percentile,
    recall_at_k,
)

# ── Shared fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def corpus() -> list[BenchPair]:
    return generate_pairs(n_target=500)


def _fresh_core(tmp_path_factory: pytest.TempPathFactory, name: str) -> MnemeCore:
    # PersistentClient with a unique path gives true per-test isolation.
    # EphemeralClient() shares its in-memory store process-wide, which
    # pollutes consolidation/recall measurements when tests run in sequence.
    d = tmp_path_factory.mktemp(name)
    return MnemeCore(
        db_path=str(d / "mneme.db"),
        _chroma_client=chromadb.PersistentClient(path=str(d / "chroma")),
    )


def _populate(core: MnemeCore, pairs: list[BenchPair]) -> dict[str, str]:
    """Store the unique memories in pairs; return content → memory_id map."""
    seen: dict[str, str] = {}
    for p in pairs:
        if p.memory_content in seen:
            continue
        mem = core.store(p.memory_content, p.memory_type, confidence=0.9)
        seen[p.memory_content] = mem.memory_id
    return seen


def _measure_recall(
    core: MnemeCore, pairs: list[BenchPair], content_to_id: dict[str, str], k: int
) -> float:
    hits = 0
    for p in pairs:
        expected_id = content_to_id[p.memory_content]
        results = core.retrieve(p.query, k=k)
        if any(r.memory_id == expected_id for r in results):
            hits += 1
    return recall_at_k(hits, len(pairs))


# ── Acceptance: Recall@10 ≥ 0.80 on 500 pairs ────────────────────────────────


@pytest.mark.slow
def test_recall_at_10_meets_acceptance(
    corpus: list[BenchPair], tmp_path_factory: pytest.TempPathFactory
) -> None:
    assert len(corpus) >= 500, f"Corpus has only {len(corpus)} pairs"
    core = _fresh_core(tmp_path_factory, "recall")
    content_to_id = _populate(core, corpus)

    recall = _measure_recall(core, corpus, content_to_id, k=10)
    assert recall >= 0.80, f"Recall@10 = {recall:.3f}, need ≥ 0.80"


# ── Acceptance: consolidation reduces duplicates ≥ 40%, recall loss ≤ 5pp ────


_CONSOLIDATION_THRESHOLD = 0.5
_CONSOLIDATION_N_BASE = 200
_CONSOLIDATION_N_DUPES = 40


def _duplicate_corpus(pairs: list[BenchPair], n_dupes: int) -> list[BenchPair]:
    """Create a corpus with ``n_dupes`` injected near-duplicate memories."""
    base = list(pairs)
    dupes: list[BenchPair] = []
    for p in pairs[:n_dupes]:
        dup_content = p.memory_content.rstrip(".") + " (also widely reported)."
        dupes.append(BenchPair(dup_content, p.memory_type, p.query))
    return base + dupes


@pytest.mark.slow
def test_consolidation_removes_duplicates_without_killing_recall(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    pairs = generate_pairs(n_target=_CONSOLIDATION_N_BASE)
    injected = _duplicate_corpus(pairs, n_dupes=_CONSOLIDATION_N_DUPES)

    core = _fresh_core(tmp_path_factory, "consolidate")
    _populate(core, injected)

    def recall_by_content() -> float:
        hits = 0
        for p in pairs:
            results = core.retrieve(p.query, k=10)
            canonical = p.memory_content.rstrip(".")
            if any(canonical in r.content for r in results):
                hits += 1
        return recall_at_k(hits, len(pairs))

    recall_before = recall_by_content()
    merged = core.consolidate(similarity_threshold=_CONSOLIDATION_THRESHOLD)

    duplicate_reduction = merged / _CONSOLIDATION_N_DUPES
    assert duplicate_reduction >= 0.40, (
        f"Consolidation merged {merged}/{_CONSOLIDATION_N_DUPES} injected duplicates "
        f"({duplicate_reduction:.0%}), need ≥ 40%"
    )
    loss = recall_before - recall_by_content()
    assert loss <= 0.05, (
        f"Recall dropped by {loss:.3f} after consolidation, budget is 0.05"
    )


# ── Acceptance: p99 retrieve_memory ≤ 200ms ──────────────────────────────────


def _latency_n() -> int:
    return int(os.environ.get("MNEME_BENCH_LATENCY_N", "2000"))


# Roadmap acceptance scale. Only at this scale does the ≤200ms SLA apply.
_ACCEPTANCE_SCALE = 100_000
_ACCEPTANCE_P99_MS = 200.0


@pytest.mark.slow
def test_retrieve_p99_latency_budget(
    tmp_path_factory: pytest.TempPathFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scalable p99 retrieve latency check.

    Default N keeps CI under a minute; set MNEME_BENCH_LATENCY_N=100000 to
    run the full Stage-3 acceptance scenario from the roadmap. At smaller N
    the SLA is not enforced — the measurement still runs so regressions in
    the benchmark pipeline itself surface.
    """
    n = _latency_n()
    core = _fresh_core(tmp_path_factory, "latency")

    corpus = generate_pairs(n_target=500)
    for p in corpus:
        core.store(p.memory_content, p.memory_type, confidence=0.9)
    for i in range(max(0, n - len(corpus))):
        core.store(
            f"Synthetic distractor #{i}: the answer is {i * 7 % 97}.",
            MemoryType.SEMANTIC,
            confidence=0.5,
        )

    # Warm the embedding model before sampling.
    for p in corpus[:5]:
        core.retrieve(p.query, k=10)

    samples_ms: list[float] = []
    for p in corpus[:200]:
        t0 = time.perf_counter()
        core.retrieve(p.query, k=10)
        samples_ms.append((time.perf_counter() - t0) * 1000.0)

    p99 = percentile(samples_ms, 99.0)
    with capsys.disabled():
        print(f"\nmneme retrieve latency @ N={n}: p99={p99:.1f}ms")

    if n >= _ACCEPTANCE_SCALE:
        assert p99 <= _ACCEPTANCE_P99_MS, (
            f"p99 retrieve latency = {p99:.1f}ms at N={n}, "
            f"budget {_ACCEPTANCE_P99_MS}ms"
        )
