"""Episode loop that drives a Planner against a MockAlfworldEnv.

A ``Planner`` is anything implementing ``decompose(goal)`` (initial plan)
and ``replan(observation)`` (recovery plan after a failed step). The
runner is generic so a Praxis-backed planner can plug in by adapting
``PraxisCore.decompose`` + ``backtrack`` to this interface.
"""
from __future__ import annotations

from typing import Iterable, Protocol

from .env import MockAlfworldEnv, Task
from .metrics import BenchmarkMetrics, EpisodeResult

MAX_STEPS = 16  # circuit-breaker against infinite loops


class Planner(Protocol):
    def decompose(self, goal: str, observation: str) -> list[str]: ...
    def replan(self, goal: str, observation: str) -> list[str]: ...


class ScriptedPlanner:
    """Returns hardcoded plans keyed by goal. Used for harness self-tests
    and as the reference implementation that future Praxis-backed
    planners must match."""

    def __init__(
        self,
        plans: dict[str, list[str]],
        recovery: dict[str, list[str]] | None = None,
    ) -> None:
        self._plans = plans
        self._recovery = recovery or {}

    def decompose(self, goal: str, observation: str) -> list[str]:
        return list(self._plans.get(goal, []))

    def replan(self, goal: str, observation: str) -> list[str]:
        return list(self._recovery.get(goal, []))


def run_episode(env: MockAlfworldEnv, planner: Planner) -> EpisodeResult:
    """Drive one episode to termination (success, exhaustion, or no plan)."""
    observation = env.reset()
    plan = planner.decompose(env.task.goal, observation)
    plan_depth = len(plan)

    steps_taken = 0
    failures_seen = 0
    failures_recovered = 0
    success = False

    while steps_taken < MAX_STEPS:
        if not plan:
            break
        action = plan.pop(0)
        result = env.step(action)
        steps_taken += 1

        if result.info.get("failed"):
            failures_seen += 1
            recovery_plan = planner.replan(env.task.goal, result.observation)
            if not recovery_plan:
                break
            plan_depth = max(plan_depth, len(recovery_plan) + steps_taken)
            plan = recovery_plan
            continue

        if result.info.get("recovered"):
            failures_recovered += 1

        if result.done:
            success = result.reward > 0
            break

    return EpisodeResult(
        task_id=env.task.task_id,
        success=success,
        steps_taken=steps_taken,
        plan_depth=plan_depth,
        failures_seen=failures_seen,
        failures_recovered=failures_recovered,
    )


def run_suite(tasks: Iterable[Task], planner: Planner) -> BenchmarkMetrics:
    metrics = BenchmarkMetrics()
    for task in tasks:
        metrics.record(run_episode(MockAlfworldEnv(task), planner))
    return metrics
