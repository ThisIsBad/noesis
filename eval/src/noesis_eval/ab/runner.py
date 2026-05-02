"""Turn-by-turn episode + suite runners for the A/B harness.

Unlike the plan-upfront ``alfworld_bench.runner`` this loop calls the
agent once per step, feeding back the full action/observation history.
That's the only shape a real Claude agent can occupy — upfront plans
don't survive contact with a stochastic env and aren't how tool-using
agents actually operate.
"""

from __future__ import annotations

import time
from typing import Iterable

from noesis_eval.alfworld_bench.env import MockAlfworldEnv, Task

from .agent import ActionOutcome, Agent, AgentTelemetry
from .results import EpisodeResult, SuiteResults

MAX_STEPS = 16
"""Circuit-breaker: episodes that haven't terminated by this many steps
are scored as failures. Matches ``alfworld_bench.runner.MAX_STEPS`` so
the two harnesses stay comparable."""


def _drain_telemetry(agent: Agent) -> AgentTelemetry:
    """Fetch the agent's per-episode counters if it exposes them.

    Agents without ``drain_telemetry`` (NullAgent, OracleAgent, the
    current stub MCPAgent) return zeroed telemetry. This keeps cost
    tracking opt-in: the A/B harness stays usable with the simple
    reference agents without forcing them to implement telemetry
    they don't have.
    """
    drain = getattr(agent, "drain_telemetry", None)
    if drain is None:
        return AgentTelemetry()
    result = drain()
    if not isinstance(result, AgentTelemetry):
        raise TypeError(
            f"{type(agent).__name__}.drain_telemetry() must return "
            f"AgentTelemetry, got {type(result).__name__}"
        )
    return result


def run_episode(env: MockAlfworldEnv, agent: Agent) -> EpisodeResult:
    """Drive one task to termination under ``agent``'s policy.

    The runner — not the agent — owns env.reset/step, the circuit
    breaker, and the history accumulation. Agents only choose actions.
    Wall time is measured here because the runner owns the loop; token
    / tool-call counts come from ``agent.drain_telemetry`` (optional)
    after the episode ends.
    """
    observation = env.reset()
    history: list[ActionOutcome] = []

    steps = 0
    failures_seen = 0
    failures_recovered = 0
    final_reward = 0.0
    success = False

    start = time.perf_counter()
    while steps < MAX_STEPS:
        action = agent.act(env.task.goal, observation, history)
        if not action:
            # Agent has nothing to say — stop before emitting an empty
            # action into the env, which would be a degenerate failure.
            break
        result = env.step(action)
        steps += 1
        history.append(
            ActionOutcome(
                action=action,
                observation=result.observation,
                reward=result.reward,
                info=dict(result.info),
            )
        )
        if result.info.get("failed"):
            failures_seen += 1
        if result.info.get("recovered"):
            failures_recovered += 1
        if result.done:
            final_reward = result.reward
            success = result.reward > 0
            break
        observation = result.observation
    wall_time_s = time.perf_counter() - start

    telemetry = _drain_telemetry(agent)

    return EpisodeResult(
        agent=agent.name,
        task_id=env.task.task_id,
        success=success,
        steps_taken=steps,
        failures_seen=failures_seen,
        failures_recovered=failures_recovered,
        final_reward=final_reward,
        tokens_in=telemetry.tokens_in,
        tokens_out=telemetry.tokens_out,
        tool_calls=telemetry.tool_calls,
        wall_time_s=wall_time_s,
    )


def run_suite(tasks: Iterable[Task], agent: Agent) -> SuiteResults:
    """Run ``agent`` across every task in ``tasks``; return aggregate."""
    results = SuiteResults(agent=agent.name)
    for task in tasks:
        results.record(run_episode(MockAlfworldEnv(task), agent))
    return results


def run_ab(
    tasks: Iterable[Task], treatment: Agent, baseline: Agent
) -> tuple[SuiteResults, SuiteResults]:
    """Run the same suite under two agents. Helper for the canonical A/B.

    Materialises ``tasks`` once so both agents see the same task order
    — iterating a generator twice silently gives the baseline a zero
    task list.
    """
    task_list = list(tasks)
    return run_suite(task_list, treatment), run_suite(task_list, baseline)
