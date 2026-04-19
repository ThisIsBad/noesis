"""ALFWorld-style harness self-tests.

Validates the env contract, episode loop, and metric aggregation using
the ScriptedPlanner reference implementation. A future PR plugs the
Praxis core into the Planner Protocol and asserts the same metrics
against the same task suite, so the acceptance numbers stay comparable.
"""
import pytest

from noesis_eval.alfworld_bench import (
    MockAlfworldEnv,
    ScriptedPlanner,
    Task,
    build_default_suite,
    build_stage3_suite,
    run_episode,
    run_suite,
)

pytestmark = pytest.mark.unit


# ── Environment contract ──────────────────────────────────────────────────────


def test_env_emits_goal_in_reset_observation():
    task = build_default_suite()[0]
    env = MockAlfworldEnv(task)
    obs = env.reset()
    assert task.goal in obs


def test_env_completes_canonical_plan():
    task = build_default_suite()[0]
    env = MockAlfworldEnv(task)
    env.reset()
    last = None
    for action in task.canonical_plan:
        last = env.step(action)
    assert last is not None
    assert last.done is True
    assert last.reward == 1.0


def test_env_rejects_invalid_action():
    task = build_default_suite()[0]
    env = MockAlfworldEnv(task)
    env.reset()
    result = env.step("teleport to mars")
    assert result.info.get("failed") is True
    assert result.done is False
    assert result.reward < 0


def test_env_blocks_step_after_termination():
    task = build_default_suite()[1]
    env = MockAlfworldEnv(task)
    env.reset()
    for action in task.canonical_plan:
        env.step(action)
    with pytest.raises(RuntimeError):
        env.step("anything")


def test_injected_failure_blocks_canonical_step():
    suite = build_default_suite()
    task = next(t for t in suite if t.task_id == "t3_recover_locked_drawer")
    env = MockAlfworldEnv(task)
    env.reset()
    result = env.step(task.canonical_plan[0])
    assert result.info.get("failed") is True
    assert result.done is False


def test_injected_failure_recovers_with_alternative():
    suite = build_default_suite()
    task = next(t for t in suite if t.task_id == "t3_recover_locked_drawer")
    env = MockAlfworldEnv(task)
    env.reset()
    env.step(task.canonical_plan[0])  # fails
    recovered = env.step(task.recovery_actions[0])
    assert recovered.info.get("recovered") is True
    # After recovery we still need the remaining canonical steps.
    final = env.step(task.canonical_plan[1])
    assert final.done is True
    assert final.reward == 1.0


# ── Episode loop ──────────────────────────────────────────────────────────────


def test_run_episode_records_success_with_correct_plan():
    task = build_default_suite()[0]
    planner = ScriptedPlanner({task.goal: list(task.canonical_plan)})
    result = run_episode(MockAlfworldEnv(task), planner)
    assert result.success is True
    assert result.steps_taken == len(task.canonical_plan)
    assert result.failures_seen == 0


def test_run_episode_records_failure_with_empty_plan():
    task = build_default_suite()[0]
    planner = ScriptedPlanner({})  # no plan known
    result = run_episode(MockAlfworldEnv(task), planner)
    assert result.success is False
    assert result.steps_taken == 0


def test_run_episode_recovers_via_replan():
    suite = build_default_suite()
    task = next(t for t in suite if t.task_id == "t3_recover_locked_drawer")
    planner = ScriptedPlanner(
        plans={task.goal: list(task.canonical_plan)},
        recovery={task.goal: [task.recovery_actions[0], task.canonical_plan[1]]},
    )
    result = run_episode(MockAlfworldEnv(task), planner)
    assert result.success is True
    assert result.failures_seen == 1
    assert result.failures_recovered == 1


def test_run_episode_aborts_when_no_recovery_plan():
    suite = build_default_suite()
    task = next(t for t in suite if t.task_id == "t5_unrecoverable_locked_room")
    planner = ScriptedPlanner(
        plans={task.goal: list(task.canonical_plan)},
        recovery={},
    )
    result = run_episode(MockAlfworldEnv(task), planner)
    assert result.success is False
    assert result.failures_seen == 1
    assert result.failures_recovered == 0


# ── Suite metrics ─────────────────────────────────────────────────────────────


def test_perfect_suite_meets_acceptance_targets():
    """Reference planner with all canonical plans + recoveries should
    clear the Stage 3 acceptance bar (>=50% success, >=50% recovery)."""
    suite = build_default_suite()
    plans = {t.goal: list(t.canonical_plan) for t in suite}
    recovery = {
        t.goal: [t.recovery_actions[0], *t.canonical_plan[1:]]
        for t in suite
        if t.recovery_actions
    }
    planner = ScriptedPlanner(plans=plans, recovery=recovery)
    metrics = run_suite(suite, planner)
    summary = metrics.summary()
    assert summary["episodes"] == len(suite)
    assert summary["success_rate"] >= 0.5
    assert summary["backtrack_recovery_rate"] >= 0.5


def test_empty_planner_records_zero_metrics():
    suite = build_default_suite()
    planner = ScriptedPlanner({})
    metrics = run_suite(suite, planner)
    assert metrics.success_rate == 0.0
    assert metrics.backtrack_recovery_rate == 0.0


def test_max_plan_depth_within_acceptance_bound():
    """Stage 3 acceptance: plan depth <=8 across the suite."""
    suite = build_default_suite()
    planner = ScriptedPlanner(
        plans={t.goal: list(t.canonical_plan) for t in suite},
    )
    metrics = run_suite(suite, planner)
    assert metrics.max_plan_depth <= 8


def test_custom_task_round_trip():
    task = Task(
        task_id="custom_one_step",
        goal="ping",
        initial_observation="You are alive.",
        canonical_plan=("pong",),
    )
    planner = ScriptedPlanner({"ping": ["pong"]})
    result = run_episode(MockAlfworldEnv(task), planner)
    assert result.success is True
    assert result.steps_taken == 1


# ── Stage-3 acceptance suite (50 injected step-failures) ─────────────────────


def test_stage3_suite_has_50_tasks_with_unique_ids_and_injections():
    suite = build_stage3_suite()
    assert len(suite) == 50
    assert len({t.task_id for t in suite}) == 50
    # The ROADMAP target is "50 injected step-failures", so every task
    # must carry exactly one injection.
    assert all(t.inject_failure_at is not None for t in suite)


def test_stage3_suite_plan_depth_within_acceptance_bound():
    """Stage-3 bound: plan depth <= 8 across the whole suite."""
    suite = build_stage3_suite()
    assert max(len(t.canonical_plan) for t in suite) <= 8


def test_stage3_suite_meets_acceptance_targets():
    """Reference planner with perfect knowledge should comfortably clear
    the Stage-3 bars (success rate >= 50%, backtrack-recovery >= 50%).
    Hitting the bars at 50 tasks guards against regressions in the env
    + runner contract; Praxis will have to meet them on its own merits
    when the real planner lands."""
    suite = build_stage3_suite()
    plans = {t.goal: list(t.canonical_plan) for t in suite}
    recovery = {
        t.goal: [t.recovery_actions[0], *t.canonical_plan[1:]]
        for t in suite
        if t.recovery_actions
    }
    planner = ScriptedPlanner(plans=plans, recovery=recovery)
    metrics = run_suite(suite, planner)

    summary = metrics.summary()
    assert summary["episodes"] == 50
    # With 45 recoverable + 5 unrecoverable, reference planner scores
    # 45/50 success and 45/50 recovery — well above the 50% floor.
    assert summary["success_rate"] >= 0.50
    assert summary["backtrack_recovery_rate"] >= 0.50
    assert summary["max_plan_depth"] <= 8

    # Sanity-check the failure accounting: every task injects once, so
    # the sum across episodes should equal the suite size.
    assert sum(e.failures_seen for e in metrics.episodes) == 50
