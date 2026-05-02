"""Tests for the Mneme-favouring memory suite.

The suite's design only pays off if:

* Every plant task's observation carries its pair's nonce verbatim
  (so a memory-capable agent has something to store).
* Every query task's canonical action is exactly its pair's nonce
  (so a memory-capable agent can win by retrieving it).
* The pairing is stable across ``build_memory_suite`` calls (so
  runs are pooled-able by ``ab history``).
* Plant and query tasks are interleaved so "short-term memory
  across one turn" isn't enough — you need to cross several
  tasks to win.

Runtime-level behaviour we pin here:

* A NullAgent (fixed action) fails every task — establishes the
  baseline floor.
* An OracleAgent given the full plans dict clears every task —
  proves the env actually accepts the nonce path.
* A baseline oracle *without* knowledge of the query nonces fails
  every query task — the suite genuinely requires information
  that isn't in the query task's own observation. That's the
  load-bearing property of "memory-favouring".
"""

from __future__ import annotations

import pytest

from noesis_eval.ab import NullAgent, OracleAgent, run_suite
from noesis_eval.alfworld_bench import build_memory_suite

pytestmark = pytest.mark.unit


# ── structural invariants ───────────────────────────────────────────────────


def test_memory_suite_has_six_tasks_three_pairs() -> None:
    """6 tasks, 3 plant + 3 query. Tiny on purpose; the first A/B
    run tells us whether to grow it."""
    suite = build_memory_suite()
    assert len(suite) == 6
    plant_ids = [t.task_id for t in suite if "_plant_" in t.task_id]
    query_ids = [t.task_id for t in suite if "_query_" in t.task_id]
    assert len(plant_ids) == 3
    assert len(query_ids) == 3


def test_memory_suite_interleaves_plants_before_queries() -> None:
    """All plants precede all queries — so a query's info was
    planted at least a few tasks earlier, forcing real persistence
    (not just last-turn recall)."""
    suite = build_memory_suite()
    names = [t.task_id for t in suite]
    plant_max_idx = max(i for i, n in enumerate(names) if "_plant_" in n)
    query_min_idx = min(i for i, n in enumerate(names) if "_query_" in n)
    assert plant_max_idx < query_min_idx


def test_memory_suite_is_deterministic() -> None:
    """Two calls to build_memory_suite produce identical task IDs,
    goals, observations, and plans. Required so `ab history` pools
    across runs correctly — a shifting task set would break that."""
    a = build_memory_suite()
    b = build_memory_suite()
    assert len(a) == len(b)
    for ta, tb in zip(a, b):
        assert ta == tb


# ── nonce plumbing: the whole suite stands or falls on this ───────────────────


def test_each_plant_observation_contains_its_pair_nonce() -> None:
    """Retrieval is impossible if the plant observation doesn't
    carry the nonce verbatim — a memory-capable agent would have
    nothing to store."""
    suite = build_memory_suite()
    plants = [t for t in suite if "_plant_" in t.task_id]
    queries = [t for t in suite if "_query_" in t.task_id]
    for plant, query in zip(plants, queries):
        assert len(query.canonical_plan) == 1, (
            "query tasks are single-action on purpose"
        )
        nonce = query.canonical_plan[0]
        # The canonical plan's action is the lowercased nonce; the
        # plant observation uses the uppercased human-readable form.
        assert nonce.upper() in plant.initial_observation, (
            f"plant {plant.task_id} observation lacks nonce "
            f"{nonce.upper()!r}: {plant.initial_observation!r}"
        )


def test_query_observations_do_not_leak_their_own_nonces() -> None:
    """If the query observation itself contained the nonce, any
    agent could solve it by parsing the prompt. The suite would
    stop measuring memory and start measuring reading
    comprehension."""
    suite = build_memory_suite()
    for query in suite:
        if "_query_" not in query.task_id:
            continue
        nonce = query.canonical_plan[0]
        assert nonce.upper() not in query.initial_observation, (
            f"{query.task_id} leaks nonce {nonce!r} in its own obs: "
            f"{query.initial_observation!r}"
        )


# ── env-level contract ──────────────────────────────────────────────────────


def test_null_agent_fails_every_task() -> None:
    """Sanity: a fixed-action agent must clear 0/6. If NullAgent
    scored above zero here the env contract would be leaky and
    the A/B numbers suspect."""
    suite = build_memory_suite()
    results = run_suite(suite, NullAgent(action="wait"))
    assert results.success_rate == 0.0


def test_oracle_with_full_plans_clears_every_task() -> None:
    """Ceiling: the env accepts the nonce path. If oracle can't
    clear 6/6, the env rejects the very action we're telling
    memory-capable agents to emit, and the suite is unsolvable by
    anyone."""
    suite = build_memory_suite()
    plans = {t.goal: list(t.canonical_plan) for t in suite}
    results = run_suite(suite, OracleAgent(plans=plans))
    assert results.success_rate == 1.0


def test_oracle_with_plant_plans_only_fails_every_query() -> None:
    """The load-bearing assertion: without access to the nonce
    (only plant-task plans known), an oracle fails every single
    query task. That's what makes the suite memory-dependent — a
    baseline agent confined to within-episode reasoning lands on
    the 0% floor on queries, regardless of how good its planner
    is. Memory (and only memory) bridges the gap."""
    suite = build_memory_suite()
    plant_plans = {
        t.goal: list(t.canonical_plan) for t in suite if "_plant_" in t.task_id
    }
    results = run_suite(suite, OracleAgent(plans=plant_plans))
    plant_successes = [
        e for e in results.episodes if "_plant_" in e.task_id and e.success
    ]
    query_successes = [
        e for e in results.episodes if "_query_" in e.task_id and e.success
    ]
    assert len(plant_successes) == 3
    assert len(query_successes) == 0


# ── CLI integration ─────────────────────────────────────────────────────────


def test_cli_knows_the_memory_suite() -> None:
    """The ``ab`` / ``run`` subcommands pick suites by name; pin
    that ``memory`` is wired in so the canonical invocation in the
    runbook keeps working."""
    from noesis_eval.ab.cli import SUITES

    assert "memory" in SUITES
    assert SUITES["memory"] is build_memory_suite
