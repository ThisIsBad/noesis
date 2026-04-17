"""Tests for the adversarial self-play harness."""

from __future__ import annotations

from logos import AdversarialSelfPlayHarness, AttackTemplate


def test_same_seed_produces_same_episode() -> None:
    harness = AdversarialSelfPlayHarness()

    first = harness.run_episode(7)
    second = harness.run_episode(7)

    assert first.to_dict() == second.to_dict()


def test_contradiction_injection_episode_passes_with_replan_defense() -> None:
    harness = AdversarialSelfPlayHarness()

    episode = harness.run_episode(0)

    assert episode.attack is AttackTemplate.CONTRADICTION_INJECTION
    assert episode.passed is True
    assert episode.blocked_safely is True
    assert episode.details["selected_protocol"] == "replan"


def test_stale_proof_replay_episode_blocks_revoked_bundle() -> None:
    harness = AdversarialSelfPlayHarness()

    episode = harness.run_episode(1)

    assert episode.attack is AttackTemplate.STALE_PROOF_REPLAY
    assert episode.passed is True
    assert "revoked" in list(episode.details["reasons"])


def test_policy_bypass_episode_blocks_before_execution() -> None:
    harness = AdversarialSelfPlayHarness()

    episode = harness.run_episode(2)

    assert episode.attack is AttackTemplate.POLICY_BYPASS
    assert episode.passed is True
    assert episode.details["policy_decision"] == "block"


def test_campaign_report_is_stable_and_regression_ready() -> None:
    harness = AdversarialSelfPlayHarness()

    report = harness.run_campaign([0, 1, 2])

    assert len(report.episodes) == 3
    assert report.average_score == 1.0
    assert report.to_dict()["schema_version"] == "1.0"
