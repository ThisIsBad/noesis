"""Unit tests for Telos' drift detection.

The core upgrade over the previous substring stub:

1. ``check_alignment`` no longer returns ``aligned=True`` for every
   action when any goal exists — it now scores the action against each
   forbidding postcondition and flags conflicts above a threshold.
2. ``reason`` is populated when a conflict fires so callers can attribute
   drift to a specific goal + postcondition.
3. The similarity function is injectable via a Protocol, so a
   sentence-transformer can replace the lexical default without touching
   the MCP surface.

These tests pin (1)–(3) and cover the "no active goals", "no forbidding
postconditions", and "empty token overlap" edge cases that would
otherwise silently regress the drift signal to 0.0.
"""
from __future__ import annotations

from noesis_schemas import GoalConstraint, GoalContract

from telos.core import TelosCore


def _goal(description: str, *forbidden: str) -> GoalContract:
    return GoalContract(
        description=description,
        postconditions=[GoalConstraint(description=d) for d in forbidden],
    )


def test_register_and_list_active():
    core = TelosCore()
    core.register(_goal("Never delete user data", "do not delete user data"))
    assert len(core.list_active()) == 1


def test_aligned_action_no_conflict():
    core = TelosCore()
    core.register(_goal("Serve users well", "never harm users"))
    result = core.check_alignment("Send a helpful response to the user")
    assert result.aligned
    assert result.drift_score == 0.0
    assert result.reason is None


def test_forbidding_postcondition_flags_similar_action():
    core = TelosCore()
    core.register(_goal("Protect user data", "do not delete user data"))
    result = core.check_alignment("delete the user data right now")
    assert not result.aligned
    assert result.drift_score == 1.0
    assert result.reason is not None
    assert "delete user data" in result.reason
    assert "similarity=" in result.reason


def test_drift_score_averages_across_active_goals():
    core = TelosCore()
    core.register(_goal("Protect data", "never delete user data"))
    core.register(_goal("Stay responsive", "never freeze the UI"))
    # Only the first goal's forbidden concept matches.
    result = core.check_alignment("delete user data now")
    assert result.drift_score == 0.5
    assert not result.aligned


def test_non_forbidding_postconditions_are_ignored():
    core = TelosCore()
    # No negation markers → not treated as forbidding.
    core.register(_goal("Ship it", "return success response"))
    result = core.check_alignment("return success response to client")
    # Token overlap is high but the postcondition isn't a prohibition,
    # so drift must be zero.
    assert result.aligned
    assert result.drift_score == 0.0


def test_drift_score_accumulates():
    core = TelosCore()
    for _ in range(5):
        core.check_alignment("neutral action")
    assert core.get_drift_score() == 0.0


def test_no_goals_always_aligned():
    core = TelosCore()
    result = core.check_alignment("anything")
    assert result.aligned
    assert result.drift_score == 0.0
    assert result.reason is None


def test_drift_log_records_every_check():
    core = TelosCore()
    core.register(_goal("Protect data", "never delete user data"))
    core.check_alignment("write a haiku")
    core.check_alignment("delete user data now")
    core.check_alignment("delete user data again")
    # Mean of [0.0, 1.0, 1.0].
    assert abs(core.get_drift_score() - (2 / 3)) < 1e-9


def test_rolling_window_caps_history():
    core = TelosCore()
    core.register(_goal("Protect data", "never delete user data"))
    # 10 drifts, then 20 clean actions.
    for _ in range(10):
        core.check_alignment("delete user data")
    for _ in range(20):
        core.check_alignment("write a haiku")
    # With window=5 we only see the last 5 (clean) entries.
    assert core.get_drift_score(window=5) == 0.0
    # With window=30 we see everything.
    assert abs(core.get_drift_score(window=30) - (10 / 30)) < 1e-9


def test_similarity_fn_is_injectable():
    """Protocol seam: a test double can replace the default lexical scorer."""
    calls: list[tuple[str, str]] = []

    def always_one(a: str, b: str) -> float:
        calls.append((a, b))
        return 1.0

    core = TelosCore(similarity_fn=always_one)
    core.register(_goal("Protect data", "never touch the database"))
    result = core.check_alignment("completely unrelated action")
    assert not result.aligned, (
        "injected similarity=1.0 must trigger a conflict even when "
        "token overlap would be zero"
    )
    assert calls, "similarity_fn should have been invoked"
