"""Acceptance-criterion benchmarks for Mneme.

Sourced from docs/ROADMAP.md lines 68-69:

- Recall@10 ≥ 0.80 on 500 query/expected-pair benchmark (semantic + episodic)
- Consolidation reduces duplicates ≥ 40% without recall loss > 5pp

Each benchmark seeds a fresh, isolated Chroma store (via the
``tmp_path`` fixture) so the assertions are reproducible and runs don't
leak state. Corpus construction uses adjective × subject combinations
to guarantee every fact has a unique, embedding-distinguishable
signature — the retriever should be able to pull the right memory back
from the top-10 with wide margin.

The benchmarks call `MnemeCore.retrieve_batch` rather than `retrieve`
in a loop. A single batched ChromaDB query amortises tokenisation and
ONNX inference across all inputs, keeping CI wall-clock under a minute
even at the 500-pair scale.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import chromadb
import pytest
from noesis_schemas import MemoryType

from mneme.core import MnemeCore

# 25 adjectives × 20 subjects = 500 unique (adjective, subject) pairs.
_ADJECTIVES = [
    "ancient",
    "azure",
    "brilliant",
    "crimson",
    "dazzling",
    "emerald",
    "frosty",
    "glistening",
    "hidden",
    "iridescent",
    "jagged",
    "luminous",
    "majestic",
    "obsidian",
    "petrified",
    "quiescent",
    "resonant",
    "serene",
    "translucent",
    "undulating",
    "verdant",
    "whispering",
    "xenolithic",
    "yawning",
    "zealous",
]
_SUBJECTS = [
    "river",
    "mountain",
    "forest",
    "desert",
    "island",
    "cavern",
    "lake",
    "valley",
    "meadow",
    "glacier",
    "temple",
    "observatory",
    "library",
    "citadel",
    "harbor",
    "lighthouse",
    "monastery",
    "catacomb",
    "amphitheater",
    "fortress",
]


def _pairs() -> Iterator[tuple[str, str]]:
    """Yield the 500 (adjective, subject) pairs in deterministic order."""
    for adj in _ADJECTIVES:
        for subj in _SUBJECTS:
            yield adj, subj


def _make_core(tmp_path: Path) -> MnemeCore:
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    return MnemeCore(
        db_path=str(tmp_path / "mneme.db"),
        _chroma_client=client,
    )


@pytest.mark.acceptance
def test_recall_at_10_above_0_80_on_500_pairs(tmp_path: Path) -> None:
    """ROADMAP line 68: Recall@10 ≥ 0.80 on 500 query/expected pairs.

    Seeds 500 semantic memories of the form
    "The <adj> <subject> is renowned for its distinctive character."
    and queries with "tell me about the <adj> <subject>". Because each
    (adj, subject) tuple is unique and the query reuses both keywords,
    embedding similarity should recover the exact memory in the top-10
    for well over 80% of queries.
    """
    core = _make_core(tmp_path)

    items = [
        (
            f"The {adj} {subj} is renowned for its distinctive character.",
            MemoryType.SEMANTIC,
            0.5,
            None,
            None,
            None,
        )
        for adj, subj in _pairs()
    ]
    stored = core.store_batch(items)
    expected_ids = [m.memory_id for m in stored]
    queries = [f"tell me about the {adj} {subj}" for adj, subj in _pairs()]

    assert len(expected_ids) == 500

    batched = core.retrieve_batch(queries, k=10)
    hits = sum(
        1
        for target_id, results in zip(expected_ids, batched)
        if any(m.memory_id == target_id for m in results)
    )

    recall_at_10 = hits / len(expected_ids)
    assert recall_at_10 >= 0.80, (
        f"Recall@10 = {recall_at_10:.2%} below 80% threshold "
        f"({hits}/{len(expected_ids)} queries retrieved expected memory)"
    )


@pytest.mark.acceptance
def test_consolidation_reduces_duplicates_without_recall_loss(
    tmp_path: Path,
) -> None:
    """ROADMAP line 69: Consolidation reduces duplicates ≥ 40% without
    recall loss > 5 percentage points.

    Seeds 20 base facts plus 20 near-duplicate paraphrases of the same
    facts, for 40 total memories. Measures baseline Recall@10 against
    the 20 base queries, runs `consolidate`, then measures
    post-consolidation Recall@10 on the same queries.

    The duplicate-reduction ratio is a dimensionless fraction so a
    smaller sample is sufficient to exercise the ROADMAP criterion
    without paying `consolidate`'s O(n) ChromaDB round-trips in CI.

    Asserts (a) consolidation removed ≥ 40% of the 20 duplicates and
    (b) post-consolidation recall dropped by no more than 5 pp.
    """
    core = _make_core(tmp_path)

    bases: list[tuple[str, str]] = []
    for adj in _ADJECTIVES[:2]:
        for subj in _SUBJECTS[:10]:
            bases.append((adj, subj))
    assert len(bases) == 20

    base_items = [
        (
            f"The {adj} {subj} is renowned for its distinctive character.",
            MemoryType.SEMANTIC,
            0.9,
            None,
            None,
            None,
        )
        for adj, subj in bases
    ]
    base_stored = core.store_batch(base_items)
    base_ids = [m.memory_id for m in base_stored]
    queries = [f"tell me about the {adj} {subj}" for adj, subj in bases]

    # Near-duplicate paraphrase for each base (lower confidence so
    # consolidation keeps the canonical copy).
    duplicate_items = [
        (
            f"A {adj} {subj} is known for its distinctive nature.",
            MemoryType.SEMANTIC,
            0.4,
            None,
            None,
            None,
        )
        for adj, subj in bases
    ]
    core.store_batch(duplicate_items)

    def _recall_at_10() -> float:
        batched = core.retrieve_batch(queries, k=10)
        hits = sum(
            1
            for target_id, results in zip(base_ids, batched)
            if any(m.memory_id == target_id for m in results)
        )
        return hits / len(base_ids)

    recall_before = _recall_at_10()

    merged = core.consolidate(similarity_threshold=0.5)
    duplicate_reduction = merged / 20  # 20 duplicate pairs seeded
    assert duplicate_reduction >= 0.40, (
        f"Consolidation merged {merged}/20 duplicates "
        f"({duplicate_reduction:.0%}), below 40% threshold"
    )

    recall_after = _recall_at_10()
    recall_loss_pp = (recall_before - recall_after) * 100
    assert recall_loss_pp <= 5.0, (
        f"Recall@10 dropped {recall_loss_pp:.1f} pp after consolidation "
        f"({recall_before:.2%} → {recall_after:.2%}), above 5 pp threshold"
    )
