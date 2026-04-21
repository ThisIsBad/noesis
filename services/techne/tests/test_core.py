from noesis_schemas import ProofCertificate

from techne.core import TechneCore


def test_store_and_retrieve_skill():
    core = TechneCore()
    core.store("retry-on-failure", "Retry failed operations", "Call tool up to 3 times")
    results = core.retrieve("retry")
    assert len(results) == 1
    assert results[0].name == "retry-on-failure"


def test_verified_flag_from_certificate():
    core = TechneCore()
    cert = ProofCertificate(
        claim_type="propositional",
        claim="strategy is correct",
        method="argument",
        verified=True,
        timestamp="2026-04-17T00:00:00+00:00",
    )
    skill = core.store(
        "proven-skill",
        "A verified strategy",
        "Do X then Y",
        certificate=cert,
    )
    assert skill.verified


def test_record_use_updates_success_rate():
    core = TechneCore()
    skill = core.store("test-skill", "test", "strategy")
    core.record_use(skill.skill_id, success=True)
    core.record_use(skill.skill_id, success=True)
    core.record_use(skill.skill_id, success=False)
    updated = core._skills[skill.skill_id]
    assert abs(updated.success_rate - 2/3) < 0.01
    assert updated.use_count == 3


def test_retrieve_verified_only_filters_unverified_description_matches():
    # Regression: operator precedence meant `verified_only=True` was bypassed
    # whenever the query matched via `description` (the left side of the OR).
    core = TechneCore()
    core.store("retry-loop", "Retry failed operations", "loop")
    assert core.retrieve("retry failed", verified_only=True) == []


def test_retrieve_verified_only_keeps_verified_matches():
    core = TechneCore()
    cert = ProofCertificate(
        claim_type="propositional",
        claim="strategy is correct",
        method="argument",
        verified=True,
        timestamp="2026-04-17T00:00:00+00:00",
    )
    core.store(
        "proven-retry",
        "Retry failed operations",
        "loop",
        certificate=cert,
    )
    results = core.retrieve("retry failed", verified_only=True)
    assert len(results) == 1
    assert results[0].name == "proven-retry"
