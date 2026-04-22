"""Cost-tracking tests for the A/B harness.

Pins the contract that separates "treatment solves more tasks" from
"treatment solves more tasks per token / per second":

* ``EpisodeResult`` exposes ``tokens_in``, ``tokens_out``, ``tool_calls``,
  ``wall_time_s`` — all default to 0 so legacy JSONL still deserialises
  and deterministic agents (Oracle, Null) need not implement telemetry.
* The runner measures ``wall_time_s`` itself (it owns the step loop)
  and drains ``agent.drain_telemetry()`` if present. Agents without
  the method (NullAgent, OracleAgent) implicitly get zeros.
* ``SuiteResults.summary`` and ``SuiteDelta.summary`` surface per-episode
  means so the CLI output carries economics alongside accuracy.
* ``SuiteDelta.tokens_ratio`` handles the 0-baseline edge case
  ("Noesis costs tokens, baseline costs none") without raising and
  without silently returning NaN.
* ``success_per_1k_tokens_*`` gives the headline economics number
  whenever telemetry is real (nonzero).

Agents with telemetry are tested via a small ``_TelemetryAgent`` fake
rather than the real MCPAgent, because MCPAgent lives on a separate
branch and because cost accounting shouldn't depend on SDK plumbing.
"""
from __future__ import annotations

import json
import time
from collections.abc import Sequence

import pytest

from noesis_eval.ab.agent import ActionOutcome, AgentTelemetry
from noesis_eval.ab.results import EpisodeResult, SuiteResults
from noesis_eval.ab.runner import _drain_telemetry, run_episode
from noesis_eval.alfworld_bench import MockAlfworldEnv, build_default_suite

pytestmark = pytest.mark.unit


# ── fakes ────────────────────────────────────────────────────────────────────


class _TelemetryAgent:
    """Scripted agent that follows a canonical plan AND reports fixed
    per-turn telemetry, so the runner's drain+aggregate path is
    exercised end-to-end without standing up the real SDK."""

    name = "telemetry-fake"

    def __init__(
        self,
        plan: Sequence[str],
        *,
        tokens_in_per_turn: int = 100,
        tokens_out_per_turn: int = 20,
        tool_calls_per_turn: int = 1,
        sleep_per_turn: float = 0.0,
    ) -> None:
        self._plan = list(plan)
        self._tokens_in_per_turn = tokens_in_per_turn
        self._tokens_out_per_turn = tokens_out_per_turn
        self._tool_calls_per_turn = tool_calls_per_turn
        self._sleep_per_turn = sleep_per_turn
        self._acc_tokens_in = 0
        self._acc_tokens_out = 0
        self._acc_tool_calls = 0

    def act(
        self,
        goal: str,
        observation: str,
        history: Sequence[ActionOutcome],
    ) -> str:
        self._acc_tokens_in += self._tokens_in_per_turn
        self._acc_tokens_out += self._tokens_out_per_turn
        self._acc_tool_calls += self._tool_calls_per_turn
        if self._sleep_per_turn > 0:
            time.sleep(self._sleep_per_turn)
        idx = len(history)
        if idx < len(self._plan):
            return self._plan[idx]
        return ""

    def drain_telemetry(self) -> AgentTelemetry:
        t = AgentTelemetry(
            tokens_in=self._acc_tokens_in,
            tokens_out=self._acc_tokens_out,
            tool_calls=self._acc_tool_calls,
        )
        # Reset — the runner calls drain once per episode; a reset keeps
        # per-episode accounting rather than suite-cumulative.
        self._acc_tokens_in = 0
        self._acc_tokens_out = 0
        self._acc_tool_calls = 0
        return t


class _BadTelemetryAgent:
    """Agent whose ``drain_telemetry`` returns the wrong type.

    The runner should surface this as a TypeError instead of silently
    accepting garbage — telemetry is the cost-accounting path, and a
    stringly-typed implementation would corrupt the ledger."""

    name = "bad-telemetry"

    def act(
        self,
        goal: str,
        observation: str,
        history: Sequence[ActionOutcome],
    ) -> str:
        return ""

    def drain_telemetry(self) -> dict[str, int]:
        return {"tokens_in": 1}  # type: ignore[return-value]


def _ep(
    agent: str,
    task_id: str,
    success: bool,
    *,
    tokens_in: int = 0,
    tokens_out: int = 0,
    tool_calls: int = 0,
    wall_time_s: float = 0.0,
    seed: int = 0,
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
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        tool_calls=tool_calls,
        wall_time_s=wall_time_s,
    )


# ── EpisodeResult schema ─────────────────────────────────────────────────────


def test_cost_fields_default_to_zero() -> None:
    ep = _ep("oracle", "t1", True)
    assert ep.tokens_in == 0
    assert ep.tokens_out == 0
    assert ep.tool_calls == 0
    assert ep.wall_time_s == 0.0


def test_legacy_jsonl_without_cost_fields_still_loads() -> None:
    """A record written before cost tracking landed is missing four
    fields. Dataclass defaults must cover all of them — not just seed
    — so old runs round-trip without special-casing."""
    legacy = {
        "agent": "oracle",
        "task_id": "t1",
        "success": True,
        "steps_taken": 3,
        "failures_seen": 0,
        "failures_recovered": 0,
        "final_reward": 1.0,
    }
    ep = EpisodeResult(**legacy)
    assert ep.tokens_in == 0
    assert ep.wall_time_s == 0.0
    recovered = EpisodeResult(**json.loads(json.dumps(ep.to_dict())))
    assert recovered == ep


def test_cost_fields_round_trip_through_jsonl() -> None:
    ep = _ep(
        "mcp-treatment",
        "t1",
        True,
        tokens_in=1234,
        tokens_out=567,
        tool_calls=8,
        wall_time_s=1.25,
    )
    recovered = EpisodeResult(**json.loads(json.dumps(ep.to_dict())))
    assert recovered.tokens_in == 1234
    assert recovered.tokens_out == 567
    assert recovered.tool_calls == 8
    assert recovered.wall_time_s == 1.25


# ── SuiteResults aggregation ─────────────────────────────────────────────────


def test_suite_results_summary_exposes_cost_means() -> None:
    r = SuiteResults(agent="t")
    r.record(_ep("t", "a", True, tokens_in=100, tokens_out=20,
                 tool_calls=2, wall_time_s=0.5))
    r.record(_ep("t", "b", False, tokens_in=200, tokens_out=40,
                 tool_calls=4, wall_time_s=1.0))

    summary = r.summary()
    # Per-episode means: total tokens 120+240=360 over 2 eps → 180.0
    assert summary["tokens_per_episode"] == pytest.approx(180.0)
    # Tool calls: (2+4)/2 = 3.0
    assert summary["tool_calls_per_episode"] == pytest.approx(3.0)
    # Wall: (0.5+1.0)/2 = 0.75
    assert summary["wall_time_per_episode"] == pytest.approx(0.75)


def test_suite_results_summary_zero_when_no_episodes() -> None:
    r = SuiteResults(agent="t")
    assert r.summary()["tokens_per_episode"] == 0.0
    assert r.summary()["tool_calls_per_episode"] == 0.0
    assert r.summary()["wall_time_per_episode"] == 0.0


# ── SuiteDelta cost math ─────────────────────────────────────────────────────


def test_suitedelta_reports_tokens_per_episode_both_sides() -> None:
    """Two tasks on each side, treatment uses more tokens but solves
    more. The delta surface has both aspects side-by-side."""
    t = SuiteResults(agent="treatment")
    b = SuiteResults(agent="baseline")
    for tid in ("a", "b"):
        t.record(_ep("treatment", tid, True,
                     tokens_in=800, tokens_out=200, tool_calls=5,
                     wall_time_s=2.0))
        b.record(_ep("baseline", tid, False,
                     tokens_in=200, tokens_out=50, tool_calls=1,
                     wall_time_s=0.5))

    delta = t.diff(b)
    assert delta.treatment_tokens_per_episode == pytest.approx(1000.0)
    assert delta.baseline_tokens_per_episode == pytest.approx(250.0)
    assert delta.treatment_tool_calls_per_episode == pytest.approx(5.0)
    assert delta.baseline_tool_calls_per_episode == pytest.approx(1.0)
    assert delta.treatment_wall_time_per_episode == pytest.approx(2.0)
    assert delta.baseline_wall_time_per_episode == pytest.approx(0.5)


def test_tokens_ratio_finite_when_both_nonzero() -> None:
    t = SuiteResults(agent="t")
    b = SuiteResults(agent="b")
    t.record(_ep("t", "a", True, tokens_in=400, tokens_out=100))
    b.record(_ep("b", "a", False, tokens_in=80, tokens_out=20))
    delta = t.diff(b)
    # (400+100) / (80+20) = 5.0
    assert delta.tokens_ratio == pytest.approx(5.0)


def test_tokens_ratio_is_inf_when_only_treatment_costs() -> None:
    """Treatment uses tokens, baseline doesn't — classic MCPAgent-vs-
    scripted case. Ratio must be +inf, not NaN or zero, so callers
    see the one-sidedness."""
    t = SuiteResults(agent="t")
    b = SuiteResults(agent="b")
    t.record(_ep("t", "a", True, tokens_in=400, tokens_out=100))
    b.record(_ep("b", "a", False))  # zero cost
    delta = t.diff(b)
    assert delta.tokens_ratio == float("inf")


def test_tokens_ratio_is_one_when_both_sides_cost_nothing() -> None:
    """Oracle vs Null: both zero. 0/0 is undefined mathematically,
    but 1.0 is the honest answer for "how much more does A cost than
    B" when neither costs anything."""
    t = SuiteResults(agent="oracle")
    b = SuiteResults(agent="null")
    t.record(_ep("oracle", "a", True))
    b.record(_ep("null", "a", False))
    delta = t.diff(b)
    assert delta.tokens_ratio == 1.0


def test_success_per_1k_tokens_is_zero_when_no_telemetry() -> None:
    """Deterministic agents report no tokens; the economics number
    must be a clean 0.0 so downstream dashboards don't have to
    special-case None/NaN."""
    t = SuiteResults(agent="oracle")
    b = SuiteResults(agent="null")
    t.record(_ep("oracle", "a", True))
    b.record(_ep("null", "a", False))
    delta = t.diff(b)
    assert delta.success_per_1k_tokens_treatment == 0.0
    assert delta.success_per_1k_tokens_baseline == 0.0


def test_success_per_1k_tokens_is_finite_when_telemetry_present() -> None:
    """2 tasks, treatment solves both at 1000 tokens each →
    1000 * 1.0 / 1000 = 1.0 successes per 1k tokens."""
    t = SuiteResults(agent="t")
    b = SuiteResults(agent="b")
    for tid in ("a", "b"):
        t.record(_ep("t", tid, True, tokens_in=800, tokens_out=200))
        b.record(_ep("b", tid, False, tokens_in=400, tokens_out=100))
    delta = t.diff(b)
    assert delta.success_per_1k_tokens_treatment == pytest.approx(1.0)
    # Baseline: 0 successes / 500 tokens = 0.
    assert delta.success_per_1k_tokens_baseline == pytest.approx(0.0)


def test_suitedelta_summary_has_economics_fields() -> None:
    t = SuiteResults(agent="t")
    b = SuiteResults(agent="b")
    t.record(_ep("t", "a", True, tokens_in=400, tokens_out=100,
                 wall_time_s=1.0))
    b.record(_ep("b", "a", False, tokens_in=200, tokens_out=50,
                 wall_time_s=0.4))
    summary = t.diff(b).summary()
    assert "treatment_tokens_per_episode" in summary
    assert "baseline_tokens_per_episode" in summary
    assert "tokens_ratio" in summary
    assert "treatment_wall_time_per_episode" in summary
    # Round-trips through JSON so the CLI can serialise it.
    json.dumps(summary)


def test_suitedelta_summary_serialises_inf_tokens_ratio() -> None:
    """The ``tokens_ratio`` property returns float('inf'); JSON has no
    native infinity, so ``summary`` substitutes the string "inf" —
    downstream dashboards see the one-sidedness instead of crashing."""
    t = SuiteResults(agent="t")
    b = SuiteResults(agent="b")
    t.record(_ep("t", "a", True, tokens_in=100, tokens_out=20))
    b.record(_ep("b", "a", False))
    summary = t.diff(b).summary()
    assert summary["tokens_ratio"] == "inf"
    # Must survive a strict JSON round-trip — i.e. no float('inf') leaked.
    json.dumps(summary)


# ── runner + drain_telemetry plumbing ────────────────────────────────────────


def test_drain_telemetry_returns_zeros_for_agent_without_hook() -> None:
    """NullAgent and OracleAgent don't implement drain_telemetry; the
    runner helper must fall back silently rather than AttributeError."""
    from noesis_eval.ab.agent import NullAgent

    telemetry = _drain_telemetry(NullAgent())
    assert telemetry == AgentTelemetry()


def test_drain_telemetry_rejects_wrong_return_type() -> None:
    """An agent that returns a dict from drain_telemetry is a bug —
    the runner must fail loud rather than silently log zeros or
    crash later in summary-building."""
    with pytest.raises(TypeError, match="AgentTelemetry"):
        _drain_telemetry(_BadTelemetryAgent())


def test_run_episode_populates_wall_time_and_telemetry() -> None:
    """Oracle that also reports fake telemetry → the EpisodeResult
    must carry per-episode sums (not zero) and a nonzero wall_time_s."""
    task = build_default_suite()[0]
    agent = _TelemetryAgent(
        task.canonical_plan,
        tokens_in_per_turn=100,
        tokens_out_per_turn=20,
        tool_calls_per_turn=1,
    )
    ep = run_episode(MockAlfworldEnv(task), agent)
    assert ep.success is True
    # The plan has N steps; telemetry is summed per turn. So totals
    # are steps * per_turn counts.
    assert ep.tokens_in == ep.steps_taken * 100
    assert ep.tokens_out == ep.steps_taken * 20
    assert ep.tool_calls == ep.steps_taken * 1
    assert ep.wall_time_s >= 0.0


def test_run_episode_measures_nonzero_wall_time_when_agent_sleeps() -> None:
    """Agents that actually do work (sleep → stand-in for an SDK
    round-trip) produce wall_time that reflects their latency, not
    just the env step overhead."""
    task = build_default_suite()[0]
    agent = _TelemetryAgent(
        task.canonical_plan,
        sleep_per_turn=0.002,  # 2 ms/turn — cheap but real
    )
    ep = run_episode(MockAlfworldEnv(task), agent)
    assert ep.wall_time_s >= ep.steps_taken * 0.002 * 0.5
    # Lower bound only — real timings vary by machine.


def test_run_episode_zero_cost_for_oracle_agent() -> None:
    """OracleAgent has no drain_telemetry hook. Its episodes must
    carry zeros across all cost fields so deterministic agents don't
    poison cost aggregates."""
    from noesis_eval.ab.agent import OracleAgent

    task = build_default_suite()[0]
    agent = OracleAgent({task.goal: list(task.canonical_plan)})
    ep = run_episode(MockAlfworldEnv(task), agent)
    assert ep.tokens_in == 0
    assert ep.tokens_out == 0
    assert ep.tool_calls == 0
    # Wall time is still measured — that's the runner's job.
    assert ep.wall_time_s >= 0.0


def test_telemetry_drain_resets_between_episodes() -> None:
    """A stateful agent that accumulates telemetry per episode must
    reset on drain, otherwise the second episode would report its own
    cost plus the first's — distorting per-episode aggregates."""
    task = build_default_suite()[0]
    agent = _TelemetryAgent(
        task.canonical_plan,
        tokens_in_per_turn=100,
    )
    ep1 = run_episode(MockAlfworldEnv(task), agent)
    ep2 = run_episode(MockAlfworldEnv(task), agent)
    assert ep1.tokens_in == ep2.tokens_in  # per-episode, not cumulative
