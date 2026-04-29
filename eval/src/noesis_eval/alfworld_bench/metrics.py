"""Aggregated benchmark metrics for the ALFWorld-style suite.

Tracks the three Praxis Stage 3 acceptance signals:
    * success rate
    * backtrack-recovery rate (fraction of injected failures recovered)
    * max plan depth observed (proxy for hallucination risk)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EpisodeResult:
    task_id: str
    success: bool
    steps_taken: int
    plan_depth: int
    failures_seen: int
    failures_recovered: int


@dataclass
class BenchmarkMetrics:
    episodes: list[EpisodeResult] = field(default_factory=list)

    def record(self, episode: EpisodeResult) -> None:
        self.episodes.append(episode)

    @property
    def success_rate(self) -> float:
        if not self.episodes:
            return 0.0
        return sum(1 for e in self.episodes if e.success) / len(self.episodes)

    @property
    def backtrack_recovery_rate(self) -> float:
        total_failures = sum(e.failures_seen for e in self.episodes)
        if total_failures == 0:
            return 0.0
        recovered = sum(e.failures_recovered for e in self.episodes)
        return recovered / total_failures

    @property
    def max_plan_depth(self) -> int:
        if not self.episodes:
            return 0
        return max(e.plan_depth for e in self.episodes)

    def summary(self) -> dict[str, float | int]:
        return {
            "episodes": len(self.episodes),
            "success_rate": round(self.success_rate, 3),
            "backtrack_recovery_rate": round(self.backtrack_recovery_rate, 3),
            "max_plan_depth": self.max_plan_depth,
        }
