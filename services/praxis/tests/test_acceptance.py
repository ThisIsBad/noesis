"""Acceptance-criterion benchmarks for Praxis.

Sourced from docs/ROADMAP.md:

- Backtrack-Recovery ≥ 50% on 50 injected step-failures.

These tests assert the numeric thresholds from the roadmap and double as
regression guards on the underlying algorithms.
"""

from __future__ import annotations

import random

import pytest

from praxis.core import PraxisCore


def _make_core(tmp_path_factory: pytest.TempPathFactory) -> PraxisCore:
    path = tmp_path_factory.mktemp("praxis") / "praxis.db"
    return PraxisCore(db_path=str(path))


def _run_backtrack_trial(core: PraxisCore, num_alternatives: int) -> bool:
    """One trial: decompose a goal, add a primary step plus N sibling
    alternatives as children of the root, fail the primary, call backtrack,
    and report whether at least one viable alternative surfaced.
    """
    plan = core.decompose("reach target state")
    primary = core.add_step(plan.plan_id, "primary attempt", risk_score=0.3)
    for i in range(num_alternatives):
        core.add_step(
            plan.plan_id,
            f"alternative attempt {i}",
            risk_score=0.3 + 0.05 * i,
        )
    core.commit_step(plan.plan_id, primary.step_id, "attempt failed", success=False)
    return bool(core.backtrack(plan.plan_id))


@pytest.mark.acceptance
def test_backtrack_recovery_at_least_50_percent(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """ROADMAP line 96: recovery rate ≥ 50% over 50 injected failures.

    Scenario distribution: 40/50 trials have 1-3 alternatives (recovery
    should succeed); 10/50 have zero alternatives (recovery must fail).
    Expected rate: 40/50 = 0.80.
    """
    rng = random.Random(20260420)

    scenarios: list[int] = [rng.randint(1, 3) for _ in range(40)] + [0] * 10
    rng.shuffle(scenarios)
    assert len(scenarios) == 50

    recoveries = 0
    for num_alts in scenarios:
        core = _make_core(tmp_path_factory)
        if _run_backtrack_trial(core, num_alts):
            recoveries += 1

    recovery_rate = recoveries / len(scenarios)
    assert recovery_rate >= 0.5, (
        f"Backtrack recovery rate {recovery_rate:.2%} below 50% threshold"
    )


@pytest.mark.acceptance
def test_backtrack_with_zero_alternatives_returns_empty(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Guard: when a failed step has no pending siblings, backtrack must
    return an empty list — not raise, not return the failed step itself.
    """
    core = _make_core(tmp_path_factory)
    plan = core.decompose("no-alternatives goal")
    only = core.add_step(plan.plan_id, "only option", risk_score=0.3)
    core.commit_step(plan.plan_id, only.step_id, "failed", success=False)
    assert core.backtrack(plan.plan_id) == []


@pytest.mark.acceptance
def test_backtrack_resets_failed_step_to_pending(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Guard: backtrack must reset FAILED → PENDING so beam search can
    reconsider the step on a retry.
    """
    from noesis_schemas import StepStatus

    core = _make_core(tmp_path_factory)
    plan = core.decompose("retry goal")
    primary = core.add_step(plan.plan_id, "try once", risk_score=0.3)
    core.add_step(plan.plan_id, "fallback", risk_score=0.4)
    core.commit_step(plan.plan_id, primary.step_id, "failed", success=False)
    core.backtrack(plan.plan_id)

    step = core._node_to_step(core._trees[plan.plan_id], primary.step_id)
    assert step.status == StepStatus.PENDING
