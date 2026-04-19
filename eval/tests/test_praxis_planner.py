"""PraxisCorePlanner adapter tests.

The adapter plugs a real ``praxis.core.PraxisCore`` into the ALFWorld
Planner Protocol. We verify two things:

1. The adapter keeps the contract honest (decompose returns canonical,
   replan returns recovery + tail) on the 5-task default suite.
2. The adapter clears the same Stage-3 acceptance bars on the 50-task
   suite that the ScriptedPlanner does. This is the real regression
   guard: any change to PraxisCore's beam search / backtrack semantics
   that would silently break end-to-end planning shows up here.

``praxis`` and ``networkx`` are soft imports — the test module skips
cleanly if either is missing, so the rest of the eval suite still runs
in a minimal environment.
"""
import pytest

pytest.importorskip("networkx")
pytest.importorskip("praxis")

from praxis.core import PraxisCore  # noqa: E402

from noesis_eval.alfworld_bench import (  # noqa: E402
    MockAlfworldEnv,
    PraxisCorePlanner,
    build_default_suite,
    build_stage3_suite,
    run_episode,
    run_suite,
)

pytestmark = pytest.mark.unit


def _core(tmp_path) -> PraxisCore:
    # PraxisCore persists to SQLite; give each test its own file so state
    # does not leak across runs.
    return PraxisCore(db_path=str(tmp_path / "praxis.db"))


def test_decompose_returns_canonical_plan(tmp_path):
    task = build_default_suite()[0]  # t1_apple_to_fridge, no injection
    planner = PraxisCorePlanner(
        core=_core(tmp_path),
        plans={task.goal: list(task.canonical_plan)},
    )
    plan = planner.decompose(task.goal, "anything")
    assert plan == list(task.canonical_plan)


def test_decompose_returns_empty_when_goal_unknown(tmp_path):
    planner = PraxisCorePlanner(core=_core(tmp_path), plans={})
    assert planner.decompose("unknown goal", "") == []


def test_replan_returns_recovery_plus_canonical_tail(tmp_path):
    suite = build_default_suite()
    task = next(t for t in suite if t.task_id == "t3_recover_locked_drawer")
    planner = PraxisCorePlanner(
        core=_core(tmp_path),
        plans={task.goal: list(task.canonical_plan)},
        recovery={task.goal: list(task.recovery_actions)},
    )
    # decompose must run first — it seeds the plan tree and records the
    # first step id the replan will mark FAILED.
    planner.decompose(task.goal, "obs")
    recovery_plan = planner.replan(task.goal, "after failure")

    assert recovery_plan[0] == task.recovery_actions[0]
    assert recovery_plan[1:] == list(task.canonical_plan[1:])


def test_replan_without_decompose_is_noop(tmp_path):
    planner = PraxisCorePlanner(
        core=_core(tmp_path),
        plans={"g": ["a"]},
        recovery={"g": ["alt"]},
    )
    assert planner.replan("g", "obs") == []


def test_end_to_end_episode_recovers_from_injection(tmp_path):
    suite = build_default_suite()
    task = next(t for t in suite if t.task_id == "t3_recover_locked_drawer")
    planner = PraxisCorePlanner(
        core=_core(tmp_path),
        plans={task.goal: list(task.canonical_plan)},
        recovery={task.goal: list(task.recovery_actions)},
    )
    result = run_episode(MockAlfworldEnv(task), planner)

    assert result.success is True
    assert result.failures_seen == 1
    assert result.failures_recovered == 1


def test_stage3_suite_clears_acceptance_targets(tmp_path):
    """End-to-end acceptance: PraxisCore must clear the same Stage-3 bars
    on 50 injected failures that ScriptedPlanner does. Success >=50%,
    backtrack-recovery >=50%, plan depth <=8."""
    suite = build_stage3_suite()
    plans = {t.goal: list(t.canonical_plan) for t in suite}
    recovery = {
        t.goal: list(t.recovery_actions)
        for t in suite
        if t.recovery_actions
    }
    planner = PraxisCorePlanner(
        core=_core(tmp_path), plans=plans, recovery=recovery
    )
    metrics = run_suite(suite, planner)
    summary = metrics.summary()

    assert summary["episodes"] == 50
    assert summary["success_rate"] >= 0.50
    assert summary["backtrack_recovery_rate"] >= 0.50
    assert summary["max_plan_depth"] <= 8
    # Every task injects exactly once — the sum across episodes must
    # match the suite size. This catches silent regressions in either
    # the env's failure injection or the adapter's replan path.
    assert sum(e.failures_seen for e in metrics.episodes) == 50
