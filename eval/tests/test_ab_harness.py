"""Unit tests for the A/B scaffold.

Pins three contracts so the follow-up PR that wires in claude-agent-sdk
only has one moving piece (the MCPAgent implementation):

1. The turn-by-turn runner reproduces the success/recovery signal the
   plan-upfront ``alfworld_bench`` runner already measures — an Oracle
   clears the Stage-3 bars, a NullAgent scores zero.
2. ``SuiteResults.diff`` correctly counts wins/losses/delta between two
   agents on the same task suite.
3. ``MCPAgent.act`` fails loudly with NotImplementedError so no-one
   accidentally runs an "A/B" where one side is a silent stub.
"""
from __future__ import annotations

import pytest

from noesis_eval.ab import (
    EpisodeResult,
    MCPAgent,
    NullAgent,
    OracleAgent,
    SuiteResults,
    run_ab,
    run_episode,
    run_suite,
)
from noesis_eval.alfworld_bench import (
    MockAlfworldEnv,
    build_default_suite,
    build_stage3_suite,
)

pytestmark = pytest.mark.unit


# ── Agent contracts ───────────────────────────────────────────────────────────


def test_oracle_solves_canonical_task() -> None:
    task = build_default_suite()[0]
    agent = OracleAgent({task.goal: list(task.canonical_plan)})
    result = run_episode(MockAlfworldEnv(task), agent)
    assert result.success is True
    assert result.steps_taken == len(task.canonical_plan)
    assert result.failures_seen == 0


def test_oracle_recovers_from_injected_failure() -> None:
    suite = build_default_suite()
    task = next(t for t in suite if t.task_id == "t3_recover_locked_drawer")
    agent = OracleAgent(
        plans={task.goal: list(task.canonical_plan)},
        recovery={task.goal: [task.recovery_actions[0]]},
    )
    result = run_episode(MockAlfworldEnv(task), agent)
    assert result.success is True
    assert result.failures_seen == 1
    assert result.failures_recovered == 1


def test_oracle_fails_when_no_recovery_path_known() -> None:
    suite = build_default_suite()
    task = next(t for t in suite if t.task_id == "t5_unrecoverable_locked_room")
    agent = OracleAgent(plans={task.goal: list(task.canonical_plan)})
    result = run_episode(MockAlfworldEnv(task), agent)
    assert result.success is False
    assert result.failures_seen == 1
    assert result.failures_recovered == 0


def test_null_agent_fails_every_task() -> None:
    """Baseline floor: a fixed nonsense action must not clear the env.
    If it did, the env contract is wrong and all other A/B numbers
    would be suspect."""
    task = build_default_suite()[0]
    agent = NullAgent(action="wait")
    result = run_episode(MockAlfworldEnv(task), agent)
    assert result.success is False
    assert result.final_reward <= 0


def test_mcp_agent_raises_until_sdk_wiring_lands() -> None:
    agent = MCPAgent()
    with pytest.raises(NotImplementedError, match="claude-agent-sdk"):
        agent.act("goal", "obs", [])


# ── Suite-level A/B ──────────────────────────────────────────────────────────


def test_oracle_clears_stage3_acceptance_bars() -> None:
    suite = build_stage3_suite()
    plans = {t.goal: list(t.canonical_plan) for t in suite}
    recovery = {
        t.goal: [t.recovery_actions[0]]
        for t in suite
        if t.recovery_actions
    }
    agent = OracleAgent(plans=plans, recovery=recovery)
    results = run_suite(suite, agent)
    summary = results.summary()
    assert summary["episodes"] == 50
    # Same thresholds the plan-upfront harness pins; the turn-by-turn
    # runner must not regress them.
    assert results.success_rate >= 0.50
    assert results.recovery_rate >= 0.50


def test_null_agent_zero_success_on_stage3() -> None:
    agent = NullAgent(action="wait")
    results = run_suite(build_stage3_suite(), agent)
    assert results.success_rate == 0.0


def test_run_ab_scores_oracle_above_null() -> None:
    """The whole point of the harness: treatment should beat baseline
    when the treatment is actually better."""
    suite = build_default_suite()
    plans = {t.goal: list(t.canonical_plan) for t in suite}
    recovery = {
        t.goal: [t.recovery_actions[0]]
        for t in suite
        if t.recovery_actions
    }
    treatment = OracleAgent(plans=plans, recovery=recovery)
    baseline = NullAgent(action="wait")
    treatment_results, baseline_results = run_ab(suite, treatment, baseline)

    delta = treatment_results.diff(baseline_results)
    assert delta.treatment == "oracle"
    assert delta.baseline == "null"
    assert delta.shared_episodes == len(suite)
    assert delta.delta > 0.4  # oracle clears 50%+, null clears 0
    assert delta.wins > 0
    assert delta.losses == 0


def test_run_ab_runs_same_task_order_for_both_agents() -> None:
    """Passing a generator twice would silently empty it on the second
    pass. ``run_ab`` materialises the suite so both agents see it."""
    suite = build_default_suite()
    treatment_results, baseline_results = run_ab(
        iter(suite),  # explicitly a generator
        OracleAgent({t.goal: list(t.canonical_plan) for t in suite}),
        NullAgent(),
    )
    assert len(treatment_results.episodes) == len(suite)
    assert len(baseline_results.episodes) == len(suite)


# ── SuiteResults.diff machinery ──────────────────────────────────────────────


def _episode(agent: str, task_id: str, success: bool) -> EpisodeResult:
    return EpisodeResult(
        agent=agent,
        task_id=task_id,
        success=success,
        steps_taken=1,
        failures_seen=0,
        failures_recovered=0,
        final_reward=1.0 if success else 0.0,
    )


def test_diff_counts_wins_and_losses_by_task_flip() -> None:
    """A win is a task where treatment succeeds but baseline didn't;
    a loss is the mirror. Ties (both or neither) contribute no signal.
    """
    treatment = SuiteResults(agent="t")
    baseline = SuiteResults(agent="b")
    for tid, t_ok, b_ok in [
        ("both_ok", True, True),       # tie, no signal
        ("both_fail", False, False),   # tie, no signal
        ("treatment_wins", True, False),
        ("baseline_wins", False, True),
    ]:
        treatment.record(_episode("t", tid, t_ok))
        baseline.record(_episode("b", tid, b_ok))

    delta = treatment.diff(baseline)
    assert delta.wins == 1
    assert delta.losses == 1
    assert delta.shared_episodes == 4


def test_diff_surfaces_task_ids_present_on_only_one_side() -> None:
    treatment = SuiteResults(agent="t")
    baseline = SuiteResults(agent="b")
    treatment.record(_episode("t", "shared", True))
    treatment.record(_episode("t", "only_t", True))
    baseline.record(_episode("b", "shared", False))
    baseline.record(_episode("b", "only_b", False))

    delta = treatment.diff(baseline)
    assert delta.shared_episodes == 1
    assert delta.only_treatment == ["only_t"]
    assert delta.only_baseline == ["only_b"]


def test_suite_results_rejects_mismatched_agent_name() -> None:
    results = SuiteResults(agent="oracle")
    with pytest.raises(ValueError, match="does not match"):
        results.record(_episode("null", "t1", False))


def test_episode_result_is_json_serialisable() -> None:
    """JSONL is the target format for recorded runs; EpisodeResult must
    round-trip through plain dicts without bespoke serialisers."""
    import json
    ep = _episode("oracle", "t1", True)
    blob = json.dumps(ep.to_dict())
    recovered = json.loads(blob)
    assert recovered["agent"] == "oracle"
    assert recovered["success"] is True
