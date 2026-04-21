"""A/B result records and paired statistics.

A single ``EpisodeResult`` captures one (agent, task, seed) outcome —
success, step count, whether recovery was triggered. Many of those
aggregate into a ``SuiteResults`` for an agent on a task suite.
``SuiteResults.diff`` compares two such runs and returns a
``SuiteDelta`` with both point estimates *and* a 95% confidence
interval plus a two-sided paired sign-test p-value, so single-number
deltas can't masquerade as signal when they're just LLM noise.

Multi-sample is first-class: tasks may appear more than once under the
same agent (run ``ab run --samples N`` or concatenate several JSONL
runs). Per-task success is then the fraction of successes across those
samples; the suite-level paired statistic is on those per-task rates.

Everything is JSONL-friendly: ``EpisodeResult.seed`` defaults to 0 so
pre-multi-sample JSONL files load verbatim.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from math import comb
from typing import Any, Sequence


@dataclass(frozen=True)
class EpisodeResult:
    agent: str
    task_id: str
    success: bool
    steps_taken: int
    failures_seen: int
    failures_recovered: int
    final_reward: float
    seed: int = 0
    """Disambiguator when the same (agent, task) is run more than once
    — lets ``ab run --samples N`` tag each replay and lets downstream
    joins pair episodes across independent invocations. Defaults to
    0 so JSONL records written before multi-sample landed still load.
    """

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SuiteResults:
    agent: str
    episodes: list[EpisodeResult] = field(default_factory=list)

    def record(self, episode: EpisodeResult) -> None:
        if episode.agent != self.agent:
            raise ValueError(
                f"episode.agent={episode.agent!r} does not match "
                f"SuiteResults.agent={self.agent!r}"
            )
        self.episodes.append(episode)

    @property
    def success_rate(self) -> float:
        """Pooled success rate over every recorded episode.

        Tasks with more samples carry proportionally more weight — for
        an unweighted per-task mean use ``diff(…).treatment_success_rate``
        which averages per-task rates.
        """
        if not self.episodes:
            return 0.0
        return sum(1 for e in self.episodes if e.success) / len(self.episodes)

    @property
    def recovery_rate(self) -> float:
        total = sum(e.failures_seen for e in self.episodes)
        if total == 0:
            return 0.0
        return sum(e.failures_recovered for e in self.episodes) / total

    def summary(self) -> dict[str, float | int | str]:
        return {
            "agent": self.agent,
            "episodes": len(self.episodes),
            "success_rate": round(self.success_rate, 3),
            "recovery_rate": round(self.recovery_rate, 3),
        }

    def diff(self, baseline: "SuiteResults") -> "SuiteDelta":
        """Compare this (treatment) run against ``baseline``.

        Groups episodes by ``task_id``; per-task success rate is the
        mean of the 0/1 success flags across all samples under that
        task. The headline ``delta`` is the unweighted mean of
        per-task (treatment_rate - baseline_rate) over shared tasks.

        On top of the point estimate:

        * ``delta_ci95`` — half-width of the 95% confidence interval
          on the mean paired difference, via Normal approximation. For
          n ≥ ~20 tasks this is accurate enough to decide "did this PR
          move the needle"; for tiny n treat it as a lower bound on
          the true CI and don't over-interpret.
        * ``p_value`` — two-sided paired sign test on per-task flips.
          Non-parametric, exact under the binomial null, and the one
          test that doesn't require assuming normality over tiny task
          counts.

        Tasks present in only one side land in ``only_treatment`` /
        ``only_baseline`` so missing data is visible rather than
        silently averaged away.
        """
        self_by_task: dict[str, list[EpisodeResult]] = defaultdict(list)
        for e in self.episodes:
            self_by_task[e.task_id].append(e)
        base_by_task: dict[str, list[EpisodeResult]] = defaultdict(list)
        for e in baseline.episodes:
            base_by_task[e.task_id].append(e)

        shared = sorted(set(self_by_task) & set(base_by_task))
        per_task: dict[str, tuple[float, float]] = {
            tid: (_rate(self_by_task[tid]), _rate(base_by_task[tid]))
            for tid in shared
        }
        samples_per_task: dict[str, tuple[int, int]] = {
            tid: (len(self_by_task[tid]), len(base_by_task[tid]))
            for tid in shared
        }

        # Wins/losses at the task level: strict inequality on the
        # per-task success rate. Single-sample tasks (the old default)
        # reduce to the original 0/1 flip semantics.
        wins = sum(1 for t, b in per_task.values() if t > b)
        losses = sum(1 for t, b in per_task.values() if b > t)

        diffs = [t - b for t, b in per_task.values()]
        mean_diff = statistics.fmean(diffs) if diffs else 0.0
        delta_ci95 = _ci95_halfwidth(diffs)

        # Paired sign test: k = min(wins, losses), n = non-tied flips.
        # Ties carry no sign and drop out — that's the textbook treatment.
        nonties = wins + losses
        p_value = (
            _two_sided_sign_test_pvalue(k=min(wins, losses), n=nonties)
            if nonties
            else 1.0
        )

        treatment_mean = (
            statistics.fmean(t for t, _ in per_task.values())
            if per_task
            else 0.0
        )
        baseline_mean = (
            statistics.fmean(b for _, b in per_task.values())
            if per_task
            else 0.0
        )

        return SuiteDelta(
            treatment=self.agent,
            baseline=baseline.agent,
            shared_tasks=len(shared),
            n_treatment_episodes=sum(
                len(self_by_task[tid]) for tid in shared
            ),
            n_baseline_episodes=sum(
                len(base_by_task[tid]) for tid in shared
            ),
            treatment_success_rate=treatment_mean,
            baseline_success_rate=baseline_mean,
            delta=mean_diff,
            delta_ci95=delta_ci95,
            p_value=p_value,
            wins=wins,
            losses=losses,
            only_treatment=sorted(set(self_by_task) - set(base_by_task)),
            only_baseline=sorted(set(base_by_task) - set(self_by_task)),
            per_task=per_task,
            samples_per_task=samples_per_task,
        )


@dataclass(frozen=True)
class SuiteDelta:
    """The A/B verdict for one (treatment, baseline) pair on a shared suite.

    All rates are computed per-task first and then averaged, so a
    long-tail task with 100 samples doesn't swamp 49 single-sample
    tasks. Use ``SuiteResults.success_rate`` if you want the pooled
    per-episode rate instead.

    * ``wins`` / ``losses`` count *tasks where the per-task rates
      differ*, strict inequality — tasks with equal rates (either
      tied at 1.0, tied at 0.0, or tied at any fractional value)
      contribute no signal and stay out of the tally.
    * ``delta`` is the unweighted mean of per-task
      (treatment_rate - baseline_rate) — a signed fraction in [-1, 1]
      that's the headline "how much does Noesis help" number.
    * ``delta_ci95`` is the Normal-approximation half-width of the
      95% confidence interval on that mean. The interval is
      ``delta ± delta_ci95``.
    * ``p_value`` is a two-sided exact binomial (sign-test) p-value
      on the win/loss count; tests ``P(treatment > baseline) ≠ 0.5``
      under ``H0``. Small task counts → near-unity p-values; don't
      mistake that for "no effect", it's "not enough data to tell".
    """
    treatment: str
    baseline: str
    shared_tasks: int
    n_treatment_episodes: int
    n_baseline_episodes: int
    treatment_success_rate: float
    baseline_success_rate: float
    delta: float
    delta_ci95: float
    p_value: float
    wins: int
    losses: int
    only_treatment: list[str]
    only_baseline: list[str]
    per_task: dict[str, tuple[float, float]]
    samples_per_task: dict[str, tuple[int, int]]

    @property
    def ci95_low(self) -> float:
        return self.delta - self.delta_ci95

    @property
    def ci95_high(self) -> float:
        return self.delta + self.delta_ci95

    @property
    def significant_at_05(self) -> bool:
        """Convenience: paired sign test clears the conventional 5% bar."""
        return self.p_value < 0.05

    @property
    def shared_episodes(self) -> int:
        """Back-compat alias — earlier callers counted episodes, not tasks.

        With single-sample runs these are equal, so nothing moves.
        """
        return self.shared_tasks

    def summary(self) -> dict[str, Any]:
        return {
            "treatment": self.treatment,
            "baseline": self.baseline,
            "shared_tasks": self.shared_tasks,
            "n_treatment_episodes": self.n_treatment_episodes,
            "n_baseline_episodes": self.n_baseline_episodes,
            "treatment_success_rate": round(self.treatment_success_rate, 3),
            "baseline_success_rate": round(self.baseline_success_rate, 3),
            "delta": round(self.delta, 3),
            "delta_ci95": round(self.delta_ci95, 3),
            "p_value": round(self.p_value, 4),
            "wins": self.wins,
            "losses": self.losses,
            "only_treatment": len(self.only_treatment),
            "only_baseline": len(self.only_baseline),
        }


# ── stats helpers ────────────────────────────────────────────────────────────


def _rate(episodes: Sequence[EpisodeResult]) -> float:
    if not episodes:
        return 0.0
    return sum(1 for e in episodes if e.success) / len(episodes)


_Z_95 = 1.959963984540054
"""Two-sided 95% z-critical from the standard Normal, which is what
``statistics.NormalDist().inv_cdf(0.975)`` returns — hard-coded so the
module doesn't instantiate a NormalDist on every diff."""


def _ci95_halfwidth(diffs: Sequence[float]) -> float:
    """Normal-approximation 95% CI half-width on the mean of ``diffs``.

    Returns 0.0 for n < 2 (can't estimate variance from a single point).
    Uses the sample stdev / sqrt(n); accurate for n ≥ ~20, optimistic
    below that — the docstring of ``SuiteDelta`` flags this.
    """
    n = len(diffs)
    if n < 2:
        return 0.0
    stderr = statistics.stdev(diffs) / math.sqrt(n)
    return _Z_95 * stderr


def _two_sided_sign_test_pvalue(k: int, n: int) -> float:
    """Exact two-sided p-value for a binomial(n, 0.5) sign test.

    ``k`` is the smaller of (wins, losses) across ``n`` non-tied tasks.
    Returns 1.0 when ``n == 0`` — with zero tasks showing any
    difference there's no signal to test, and a p-value below 1 would
    falsely imply otherwise.
    """
    if n <= 0:
        return 1.0
    if k < 0 or k > n:
        raise ValueError(f"k={k} out of range for n={n}")
    # Two-sided symmetric p: 2 * P(X <= k) under Bin(n, 0.5), capped at 1.
    tail = sum(comb(n, i) for i in range(k + 1)) / (2 ** n)
    return float(min(1.0, 2 * tail))
