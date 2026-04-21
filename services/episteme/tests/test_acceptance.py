"""Acceptance-criterion benchmarks for Episteme.

Sourced from docs/ROADMAP.md lines 149-150:

- ECE ≤ 0.10 over 200 diverse claims (Stage 3 standard)
- Brier score ≤ 0.20 per domain

Each test constructs a well-calibrated prediction history whose aggregate
and per-domain statistics must stay inside the ROADMAP thresholds. The
construction uses exact outcome counts so the benchmarks are fully
deterministic — if the underlying metrics drift (e.g. ECE definition
changes from single-bucket to bucketed and breaks the invariant) the
suite will surface the regression.
"""
from __future__ import annotations

import pytest

from episteme.core import EpistemeCore

# Four synthetic domains. For each, we fix a confidence level and an
# exact correct/incorrect split such that avg_confidence == accuracy.
# This yields ECE = 0 and keeps Brier comfortably under 0.20 because we
# avoid the mid-confidence regime (p ≈ 0.5) where Brier peaks.
_CALIBRATED_DOMAINS = [
    # (domain,     confidence, samples, correct)
    ("weather",    0.9,        50,      45),   # 45/50 = 0.90; Brier 0.09
    ("markets",    0.8,        50,      40),   # 40/50 = 0.80; Brier 0.16
    ("sports",     0.2,        50,      10),   # 10/50 = 0.20; Brier 0.16
    ("physics",    0.1,        50,      5),    #  5/50 = 0.10; Brier 0.09
]


def _seed_calibrated_history(core: EpistemeCore) -> int:
    """Populate ``core`` with the calibrated corpus. Returns total samples."""
    total = 0
    for domain, confidence, samples, correct in _CALIBRATED_DOMAINS:
        for i in range(samples):
            pred = core.log_prediction(
                f"{domain} claim #{i}", confidence=confidence, domain=domain,
            )
            core.log_outcome(pred.prediction_id, correct=(i < correct))
        total += samples
    return total


@pytest.mark.acceptance
def test_ece_under_0_10_on_200_diverse_claims() -> None:
    """ROADMAP line 149: ECE ≤ 0.10 over 200 diverse claims.

    The seeded corpus has 200 resolved predictions across 4 domains,
    each exactly calibrated (per-domain accuracy == per-domain
    confidence). Aggregate ECE (|avg_confidence - accuracy|) is
    therefore 0.0 — well inside the 0.10 envelope.
    """
    core = EpistemeCore()
    total = _seed_calibrated_history(core)
    assert total == 200

    report = core.get_calibration()
    assert report.sample_size == 200
    assert report.ece <= 0.10, f"ECE {report.ece:.4f} above 0.10 threshold"


@pytest.mark.acceptance
def test_brier_under_0_20_per_domain() -> None:
    """ROADMAP line 150: Brier score ≤ 0.20 per domain.

    We call `get_calibration(domain=...)` for each domain in the seeded
    corpus and assert its Brier score stays inside the envelope. With
    confidences chosen at 0.1 / 0.2 / 0.8 / 0.9 and matching accuracies,
    the worst-case per-domain Brier is 0.16.
    """
    core = EpistemeCore()
    _seed_calibrated_history(core)

    for domain, _, _, _ in _CALIBRATED_DOMAINS:
        report = core.get_calibration(domain=domain)
        assert report.sample_size == 50
        assert report.brier_score <= 0.20, (
            f"Domain {domain!r} Brier {report.brier_score:.4f} above 0.20"
        )


@pytest.mark.acceptance
def test_ece_threshold_detects_systematic_overconfidence() -> None:
    """Regression tripwire: a deliberately mis-calibrated corpus must breach
    the 0.10 ECE threshold.

    If someone later swaps `get_calibration`'s ECE for a metric that
    silently ignores systematic overconfidence, this test fails and
    surfaces the semantic drift.
    """
    core = EpistemeCore()
    # 200 claims at confidence 0.9 with only 50% accuracy → avg_conf 0.9,
    # accuracy 0.5, ECE = 0.4, which is clearly above 0.10.
    for i in range(200):
        pred = core.log_prediction(
            f"overconfident #{i}", confidence=0.9, domain="mis_cal",
        )
        core.log_outcome(pred.prediction_id, correct=(i < 100))

    report = core.get_calibration()
    assert report.ece > 0.10, (
        f"Mis-calibrated corpus ECE {report.ece:.4f} unexpectedly inside "
        "0.10 threshold — metric may have drifted"
    )
