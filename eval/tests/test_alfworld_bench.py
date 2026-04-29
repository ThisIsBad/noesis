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
from noesis_eval.alfworld_bench.env import _action_matches, _tokenize

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


# ── Fuzzy action matching (paraphrase tolerance) ─────────────────────────────
#
# The original env did exact-string equality against each step of the
# canonical plan, which meant a real LLM agent emitting a natural
# paraphrase ("walk from the lobby to the conference room" vs
# "walk to conference room") got its action rejected, failed every
# turn, and burned the full MAX_STEPS budget. A/B deltas on the
# memory suite collapsed to noise. These tests pin that:
#
# * all previously-passing exact-match cases still succeed (100%
#   overlap is a subset of ≥60%),
# * common paraphrases — added filler words, articles, reordered
#   prepositions — also succeed,
# * genuinely different actions still fail (we didn't accidentally
#   trade measurement rigor for permissiveness).


def test_tokenize_strips_stopwords_and_punctuation():
    assert _tokenize("walk to the conference room.") == ["walk", "conference", "room"]


def test_tokenize_preserves_internal_punctuation_in_nonces():
    # Memory-suite nonces like K42-N9T rely on the hyphen staying put;
    # if _tokenize split on '-' the query canonical action would never
    # match the agent's emission.
    assert _tokenize("enter K42-N9T") == ["enter", "k42-n9t"]


def test_action_matches_exact_string_still_accepted():
    assert _action_matches("walk to conference room", "walk to conference room") is True


def test_action_matches_accepts_paraphrase_with_added_fillers():
    """The memory-suite regression: agent adds 'from the lobby' ahead
    of the canonical phrasing and the env must still accept it."""
    assert (
        _action_matches(
            "walk from the lobby to the conference room",
            "walk to conference room",
        )
        is True
    )


def test_action_matches_accepts_reordered_prepositions():
    assert (
        _action_matches(
            "place the flasks back on the shelf",
            "place flasks on shelf",
        )
        is True
    )


def test_action_matches_rejects_unrelated_action():
    assert _action_matches("teleport to mars", "pick up apple") is False


def test_action_matches_rejects_partial_content_below_threshold():
    """If the agent drops one of two content tokens it's 50% overlap —
    below the 60% floor. This is the guardrail against over-accepting
    sloppy paraphrases."""
    assert _action_matches("pick the orange", "pick up apple") is False


def test_env_accepts_paraphrased_canonical_action():
    """The load-bearing regression fix: the memory suite's first plant
    task rejects the agent's natural phrasing under exact-match, which
    was the whole reason the A/B went noiseless. Pin that the env
    now accepts it."""
    task = Task(
        task_id="paraphrase_probe",
        goal="walk from the lobby to the conference room",
        initial_observation="You are in the lobby.",
        canonical_plan=("walk to conference room",),
    )
    env = MockAlfworldEnv(task)
    env.reset()
    result = env.step("walk from the lobby to the conference room")
    assert result.done is True
    assert result.reward == 1.0


def test_env_accepts_paraphrased_recovery_action():
    task = Task(
        task_id="paraphrase_recover",
        goal="retrieve the key",
        initial_observation="The drawer is locked; a paperclip is on the floor.",
        canonical_plan=("open drawer", "take key from drawer"),
        inject_failure_at=0,
        recovery_actions=("pick paperclip and unlock drawer",),
    )
    env = MockAlfworldEnv(task)
    env.reset()
    env.step("open drawer")  # fails (injected)
    recovered = env.step("pick up the paperclip and unlock the drawer")
    assert recovered.info.get("recovered") is True


# ── Consecutive-fail circuit breaker ─────────────────────────────────────────
#
# Without a cap, an agent that can't find the canonical phrasing burns
# all 16 MAX_STEPS before the runner terminates the episode. That's a
# 16× token-cost multiplier on design-mismatched tasks and the main
# reason the first memory-suite A/B runs blew past budget. These tests
# pin that after N consecutive invalid actions the env terminates the
# episode itself, letting the runner move on.


def test_consecutive_failures_trip_circuit_breaker():
    task = Task(
        task_id="stuck_agent",
        goal="do the thing",
        initial_observation="Start.",
        canonical_plan=("pick up apple",),
    )
    env = MockAlfworldEnv(task, max_consecutive_fails=3)
    env.reset()
    r1 = env.step("nonsense one")
    r2 = env.step("nonsense two")
    assert r1.done is False and r2.done is False
    r3 = env.step("nonsense three")
    assert r3.done is True
    assert r3.info.get("aborted") is True
    assert r3.info.get("consecutive_fails") == 3
    assert r3.reward == -1.0


def test_successful_action_resets_consecutive_fail_counter():
    """Agents that fumble a few turns and then recover must not get
    penalised for earlier mistakes — the circuit breaker is about
    *ongoing* thrash, not total fails."""
    task = Task(
        task_id="fumble_then_solve",
        goal="two-step",
        initial_observation="Start.",
        canonical_plan=("step one", "step two"),
    )
    env = MockAlfworldEnv(task, max_consecutive_fails=3)
    env.reset()
    env.step("wrong a")
    env.step("wrong b")
    ok = env.step("step one")  # counter resets here
    assert ok.info.get("failed") is not True
    # After the reset we should still have the full fail budget.
    env.step("wrong c")
    env.step("wrong d")
    final = env.step("step two")
    assert final.done is True
    assert final.reward == 1.0


def test_circuit_breaker_default_threshold_is_five():
    """Guard the default — a surprise tightening would silently cut
    into agents' retry budget and drop success rates."""
    task = Task(
        task_id="default_thresh",
        goal="g",
        initial_observation=".",
        canonical_plan=("ok",),
    )
    env = MockAlfworldEnv(task)
    env.reset()
    for _ in range(4):
        assert env.step("nope").done is False
    aborted = env.step("nope")
    assert aborted.done is True
    assert aborted.info.get("aborted") is True


def test_circuit_breaker_blocks_further_steps_after_abort():
    task = Task(
        task_id="no_step_after_abort",
        goal="g",
        initial_observation=".",
        canonical_plan=("ok",),
    )
    env = MockAlfworldEnv(task, max_consecutive_fails=1)
    env.reset()
    env.step("nope")  # trips breaker on first fail
    with pytest.raises(RuntimeError):
        env.step("anything")
