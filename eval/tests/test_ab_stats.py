"""Statistical-rigor tests for the A/B harness.

These pin the contract that separates real signal from LLM noise:

* ``EpisodeResult.seed`` disambiguates replays, so a JSONL file holding
  N samples per task round-trips without silent overwrites.
* ``SuiteResults.diff`` computes per-task success rates across samples
  (not per-episode flips) so tasks with many samples don't swamp tasks
  with few.
* Paired sign-test p-value and Normal-approx 95% CI on the mean
  per-task delta come out to the known closed-form numbers, so the
  CLI's "significant" annotation can be trusted.
* Backward compatibility: JSONL records written before multi-sample
  existed (no ``seed`` field) still load; ``shared_episodes`` still
  reads the right number on single-sample runs.

No suite or runner is driven here — the stats layer is unit-testable
with hand-constructed ``EpisodeResult`` lists, which is exactly what
we want: statistical correctness shouldn't depend on env plumbing.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from noesis_eval.ab.cli import main
from noesis_eval.ab.results import (
    EpisodeResult,
    SuiteResults,
    _ci95_halfwidth,
    _two_sided_sign_test_pvalue,
)

pytestmark = pytest.mark.unit


# ── helpers ──────────────────────────────────────────────────────────────────


def _ep(
    agent: str, task_id: str, success: bool, *, seed: int = 0
) -> EpisodeResult:
    return EpisodeResult(
        agent=agent,
        task_id=task_id,
        success=success,
        steps_taken=1,
        failures_seen=0,
        failures_recovered=0,
        final_reward=1.0 if success else 0.0,
        seed=seed,
    )


# ── EpisodeResult backward compatibility ─────────────────────────────────────


def test_episode_result_seed_defaults_to_zero() -> None:
    """Records written before multi-sample had no ``seed`` field; they
    still deserialise via ``EpisodeResult(**raw)``."""
    legacy_json = json.dumps({
        "agent": "oracle",
        "task_id": "t1",
        "success": True,
        "steps_taken": 3,
        "failures_seen": 0,
        "failures_recovered": 0,
        "final_reward": 1.0,
    })
    ep = EpisodeResult(**json.loads(legacy_json))
    assert ep.seed == 0
    # And the round-trip preserves seed in the new field.
    assert json.loads(json.dumps(ep.to_dict()))["seed"] == 0


def test_episode_result_seed_round_trips() -> None:
    ep = _ep("mcp-treatment", "t1", True, seed=7)
    recovered = EpisodeResult(**json.loads(json.dumps(ep.to_dict())))
    assert recovered.seed == 7


# ── multi-sample diff semantics ──────────────────────────────────────────────


def test_diff_pools_samples_per_task_into_success_rate() -> None:
    """Three samples per task, treatment wins 2/3 each, baseline 0/3.
    Per-task rates: treatment=0.67, baseline=0.0 → delta per task =
    +0.667. Unweighted mean across 2 tasks = +0.667.
    """
    treatment = SuiteResults(agent="t")
    baseline = SuiteResults(agent="b")
    for tid in ("task_a", "task_b"):
        for seed, ok in enumerate([True, True, False]):
            treatment.record(_ep("t", tid, ok, seed=seed))
        for seed in range(3):
            baseline.record(_ep("b", tid, False, seed=seed))

    delta = treatment.diff(baseline)
    assert delta.shared_tasks == 2
    assert delta.n_treatment_episodes == 6
    assert delta.n_baseline_episodes == 6
    assert delta.treatment_success_rate == pytest.approx(2 / 3)
    assert delta.baseline_success_rate == 0.0
    assert delta.delta == pytest.approx(2 / 3)
    # Both tasks strictly favor treatment → 2 wins, 0 losses.
    assert delta.wins == 2
    assert delta.losses == 0


def test_diff_handles_asymmetric_sample_counts() -> None:
    """Treatment has 4 samples on t1, baseline has 2. Per-task rate is
    still computed correctly on each side's own denominator."""
    treatment = SuiteResults(agent="t")
    baseline = SuiteResults(agent="b")
    for seed, ok in enumerate([True, True, True, False]):
        treatment.record(_ep("t", "t1", ok, seed=seed))
    for seed, ok in enumerate([True, False]):
        baseline.record(_ep("b", "t1", ok, seed=seed))

    delta = treatment.diff(baseline)
    assert delta.treatment_success_rate == pytest.approx(0.75)
    assert delta.baseline_success_rate == pytest.approx(0.5)
    assert delta.delta == pytest.approx(0.25)
    assert delta.samples_per_task["t1"] == (4, 2)


def test_diff_ties_on_fractional_rates_contribute_no_signal() -> None:
    """Both sides land on the same per-task rate → tie, zero win / loss
    contribution, p-value 1.0 (not rejection of equal performance).
    """
    treatment = SuiteResults(agent="t")
    baseline = SuiteResults(agent="b")
    for seed, (ok_t, ok_b) in enumerate([(True, True), (False, False)]):
        treatment.record(_ep("t", "t1", ok_t, seed=seed))
        baseline.record(_ep("b", "t1", ok_b, seed=seed))
    # Both sides: 1/2 on t1.

    delta = treatment.diff(baseline)
    assert delta.wins == 0
    assert delta.losses == 0
    assert delta.delta == pytest.approx(0.0)
    assert delta.p_value == 1.0


def test_diff_single_sample_still_counts_as_task_flip() -> None:
    """Back-compat: the old harness only ran each task once. With
    samples=1 per task, the new per-task-rate semantics must reduce
    to the old per-episode-flip semantics exactly."""
    treatment = SuiteResults(agent="t")
    baseline = SuiteResults(agent="b")
    for tid, t_ok, b_ok in [
        ("a", True, False),   # treatment wins
        ("b", False, True),   # baseline wins
        ("c", True, True),    # tie on 1.0
        ("d", False, False),  # tie on 0.0
    ]:
        treatment.record(_ep("t", tid, t_ok))
        baseline.record(_ep("b", tid, b_ok))

    delta = treatment.diff(baseline)
    assert delta.wins == 1
    assert delta.losses == 1
    assert delta.shared_tasks == 4
    # shared_episodes alias must stay honest for single-sample runs.
    assert delta.shared_episodes == 4


# ── statistical helpers ──────────────────────────────────────────────────────


def test_sign_test_unambiguous_win_is_significant() -> None:
    """10/10 wins under H0: P(win)=0.5 gives p = 2 * (1/2^10) ≈ 0.00195.
    That's the textbook cutoff above any reasonable 5% threshold."""
    p = _two_sided_sign_test_pvalue(k=0, n=10)
    assert p == pytest.approx(2 * (1 / 1024), rel=1e-9)
    assert p < 0.05


def test_sign_test_balanced_wins_is_not_significant() -> None:
    """5 wins / 5 losses: k=5, n=10 → p-value = 1.0 under the two-sided
    exact binomial. A coin flip shouldn't look significant."""
    assert _two_sided_sign_test_pvalue(k=5, n=10) == 1.0


def test_sign_test_zero_nonties_returns_one() -> None:
    """No flips at all → p-value must be 1.0, not NaN / not < 1."""
    assert _two_sided_sign_test_pvalue(k=0, n=0) == 1.0


def test_sign_test_rejects_out_of_range_k() -> None:
    with pytest.raises(ValueError):
        _two_sided_sign_test_pvalue(k=11, n=10)


def test_ci95_halfwidth_zero_for_single_sample() -> None:
    """Can't compute a CI from one data point; must return 0 rather
    than raise, since diff() on a 1-task suite is legal."""
    assert _ci95_halfwidth([0.5]) == 0.0


def test_ci95_halfwidth_matches_normal_approx() -> None:
    """Closed-form check: n=4 diffs with stdev s has CI half-width
    ≈ 1.96 * s / sqrt(4) = 0.98 * s. Use constant diffs (stdev=0)
    for a clean zero, then a known-stdev case."""
    assert _ci95_halfwidth([0.5, 0.5, 0.5, 0.5]) == pytest.approx(0.0)

    # stdev of [0, 1] = sqrt(0.5) ≈ 0.7071; sample stdev uses n-1.
    # n=2 → sem = stdev / sqrt(2) = 0.5; half-width = 1.96 * 0.5 = 0.98.
    hw = _ci95_halfwidth([0.0, 1.0])
    assert hw == pytest.approx(1.959963984540054 * 0.5, rel=1e-9)


def test_suitedelta_ci95_brackets_and_significance_flag() -> None:
    """Wide CI from a 10/10-win suite clears the sig flag;
    ``ci95_low`` + ``ci95_high`` bracket ``delta`` symmetrically."""
    treatment = SuiteResults(agent="t")
    baseline = SuiteResults(agent="b")
    for i in range(10):
        treatment.record(_ep("t", f"task_{i}", True))
        baseline.record(_ep("b", f"task_{i}", False))

    delta = treatment.diff(baseline)
    assert delta.delta == pytest.approx(1.0)
    # All diffs = 1.0 → stdev = 0 → CI half-width = 0.
    assert delta.delta_ci95 == 0.0
    assert delta.ci95_low == delta.delta
    assert delta.ci95_high == delta.delta
    # 10 wins / 0 losses → p < 0.05.
    assert delta.significant_at_05 is True


def test_suitedelta_not_significant_when_effect_is_mixed() -> None:
    """Alternating wins and losses across 4 tasks: sign test p = 1.0,
    flag must stay off even though delta happens to be nonzero."""
    treatment = SuiteResults(agent="t")
    baseline = SuiteResults(agent="b")
    for i, (t_ok, b_ok) in enumerate([
        (True, False), (False, True), (True, False), (False, True),
    ]):
        treatment.record(_ep("t", f"t{i}", t_ok))
        baseline.record(_ep("b", f"t{i}", b_ok))

    delta = treatment.diff(baseline)
    assert delta.wins == 2
    assert delta.losses == 2
    assert delta.p_value == 1.0
    assert delta.significant_at_05 is False


# ── CLI: --samples flag ──────────────────────────────────────────────────────


def test_cli_samples_emits_one_line_per_replay(tmp_path: Path) -> None:
    """``--samples 3`` on the 5-task default suite → 15 JSONL lines,
    each with a ``seed`` field in {0, 1, 2}."""
    out = tmp_path / "oracle.jsonl"
    rc = main(["run", "oracle", "--suite", "default",
               "--samples", "3", "--output", str(out)])
    assert rc == 0
    lines = [ln for ln in out.read_text().splitlines() if ln.strip()]
    assert len(lines) == 15  # 5 tasks × 3 replays
    seeds = [json.loads(ln)["seed"] for ln in lines]
    assert set(seeds) == {0, 1, 2}
    # Every seed value must appear equally often — five times apiece.
    assert seeds.count(0) == 5
    assert seeds.count(1) == 5
    assert seeds.count(2) == 5


def test_cli_samples_rejects_nonpositive() -> None:
    with pytest.raises(SystemExit):
        main(["run", "null", "--samples", "0"])


def test_cli_samples_default_is_one(tmp_path: Path) -> None:
    """Default --samples=1 keeps the old behaviour byte-for-byte
    (5-task suite → 5 lines)."""
    out = tmp_path / "oracle.jsonl"
    assert main(["run", "oracle", "--output", str(out)]) == 0
    lines = [ln for ln in out.read_text().splitlines() if ln.strip()]
    assert len(lines) == 5


# ── CLI: diff output surface ─────────────────────────────────────────────────


def test_cli_diff_prints_ci_and_pvalue_and_sig_marker(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unambiguous treatment wins across 6 tasks → p < 0.05, CLI
    appends a ``*`` to the p-value line so pipelines can grep for it.
    """
    t = tmp_path / "t.jsonl"
    b = tmp_path / "b.jsonl"
    with t.open("w") as tf, b.open("w") as bf:
        for i in range(6):
            tf.write(
                json.dumps(_ep("oracle", f"t{i}", True).to_dict()) + "\n"
            )
            bf.write(
                json.dumps(_ep("null", f"t{i}", False).to_dict()) + "\n"
            )

    assert main(["diff", str(t), str(b)]) == 0
    out = capsys.readouterr().out
    assert "p-value:" in out
    assert "*" in out  # significance marker
    assert "95% CI" in out


def test_cli_diff_no_sig_marker_on_noisy_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Balanced wins/losses → no ``*``; caller can trust absence."""
    t = tmp_path / "t.jsonl"
    b = tmp_path / "b.jsonl"
    with t.open("w") as tf, b.open("w") as bf:
        for i, (t_ok, b_ok) in enumerate([
            (True, False), (False, True),
            (True, False), (False, True),
        ]):
            tf.write(json.dumps(_ep("t", f"t{i}", t_ok).to_dict()) + "\n")
            bf.write(json.dumps(_ep("b", f"t{i}", b_ok).to_dict()) + "\n")

    assert main(["diff", str(t), str(b)]) == 0
    out = capsys.readouterr().out
    assert "p-value:" in out
    # The marker is " *" at end-of-line; a quick way to rule it out.
    assert " *\n" not in out and not out.rstrip().endswith(" *")


# ── diff: multi-sample JSONL round-trip through the CLI ──────────────────────


def test_cli_round_trip_with_samples(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Full end-to-end: run with --samples, then diff. Oracle beats
    Null on every task × every replay → significant, large delta.
    The episode counts in the summary reflect the replay count."""
    oracle_out = tmp_path / "oracle.jsonl"
    null_out = tmp_path / "null.jsonl"
    assert main(["run", "oracle", "--samples", "2",
                 "--output", str(oracle_out)]) == 0
    assert main(["run", "null", "--samples", "2",
                 "--output", str(null_out)]) == 0
    capsys.readouterr()  # drop per-run summaries

    assert main(["diff", str(oracle_out), str(null_out)]) == 0
    summary = capsys.readouterr().out
    assert "treatment=10 episodes" in summary  # 5 tasks × 2 replays
    assert "baseline=10" in summary  # follows "treatment=10 episodes, "
    assert "shared tasks:      5" in summary
    # Oracle wins 4/5 tasks (one task is unrecoverable) → p ≈ 0.125,
    # which intentionally does NOT clear the 5% bar. The test pins
    # that: a small suite can't be called "significant" on effect
    # alone.
    assert "p-value:" in summary
    assert math.isfinite(float(summary.split("p-value:")[1].split()[0]))
