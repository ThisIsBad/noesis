"""A/B result records.

A single ``EpisodeResult`` captures one (agent, task) outcome —
success, step count, whether recovery was triggered. Many of those
aggregate into a ``SuiteResults`` for an agent on a task suite.
``SuiteResults.diff`` compares two such runs for the A/B verdict.

Everything is JSONL-friendly: a follow-up CLI will dump episode
records one-per-line so multiple independent runs can be merged and
variance measured.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class EpisodeResult:
    agent: str
    task_id: str
    success: bool
    steps_taken: int
    failures_seen: int
    failures_recovered: int
    final_reward: float

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

        Pairs episodes by ``task_id``; tasks present in one side only
        show up in ``only_treatment`` / ``only_baseline`` so missing
        data is visible rather than silently averaged away.
        """
        self_by_task = {e.task_id: e for e in self.episodes}
        base_by_task = {e.task_id: e for e in baseline.episodes}

        shared = set(self_by_task) & set(base_by_task)
        per_task: dict[str, tuple[bool, bool]] = {
            tid: (base_by_task[tid].success, self_by_task[tid].success)
            for tid in shared
        }
        wins = sum(1 for b, t in per_task.values() if t and not b)
        losses = sum(1 for b, t in per_task.values() if b and not t)

        return SuiteDelta(
            treatment=self.agent,
            baseline=baseline.agent,
            shared_episodes=len(shared),
            treatment_success_rate=self.success_rate,
            baseline_success_rate=baseline.success_rate,
            wins=wins,
            losses=losses,
            only_treatment=sorted(set(self_by_task) - set(base_by_task)),
            only_baseline=sorted(set(base_by_task) - set(self_by_task)),
            per_task=per_task,
        )


@dataclass(frozen=True)
class SuiteDelta:
    """The A/B verdict for one (treatment, baseline) pair on a shared suite.

    * ``wins`` / ``losses`` count *per-task flips* — episodes where one
      agent succeeds and the other doesn't. Agents that both pass or
      both fail a task don't contribute signal and stay out of the
      tally.
    * ``delta`` is the mean of (treatment_success - baseline_success)
      over shared episodes — a signed fraction in [-1, 1] that's the
      headline "how much does Noesis help" number.
    """
    treatment: str
    baseline: str
    shared_episodes: int
    treatment_success_rate: float
    baseline_success_rate: float
    wins: int
    losses: int
    only_treatment: list[str]
    only_baseline: list[str]
    per_task: dict[str, tuple[bool, bool]]

    @property
    def delta(self) -> float:
        return self.treatment_success_rate - self.baseline_success_rate

    def summary(self) -> dict[str, Any]:
        return {
            "treatment": self.treatment,
            "baseline": self.baseline,
            "shared_episodes": self.shared_episodes,
            "treatment_success_rate": round(self.treatment_success_rate, 3),
            "baseline_success_rate": round(self.baseline_success_rate, 3),
            "delta": round(self.delta, 3),
            "wins": self.wins,
            "losses": self.losses,
            "only_treatment": len(self.only_treatment),
            "only_baseline": len(self.only_baseline),
        }
