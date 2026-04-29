"""Retrieval metrics used by Mneme acceptance benchmarks."""

from __future__ import annotations

import math


def recall_at_k(hits: int, total: int) -> float:
    if total == 0:
        return 0.0
    return hits / total


def percentile(samples: list[float], p: float) -> float:
    """Nearest-rank percentile, ``p`` in [0, 100]."""
    if not samples:
        raise ValueError("percentile of empty sample")
    if not 0.0 <= p <= 100.0:
        raise ValueError(f"percentile must be in [0, 100], got {p}")
    ordered = sorted(samples)
    rank = max(1, math.ceil((p / 100.0) * len(ordered)))
    return ordered[rank - 1]
