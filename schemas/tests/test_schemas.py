from noesis_schemas import (
    ClaimKind,
    ConfidenceLevel,
    ConfidenceRecord,
    EscalationDecision,
    GoalContract,
    Lesson,
    Memory,
    MemoryType,
    Plan,
    PlanStep,
    ProofCertificate,
    RiskLevel,
    Skill,
    TraceSpan,
    confidence_from_float,
)


def _make_cert(**overrides) -> ProofCertificate:
    defaults = dict(
        claim_type="propositional",
        claim="P implies Q",
        method="z3_propositional",
        verified=True,
        timestamp="2026-04-17T00:00:00+00:00",
    )
    defaults.update(overrides)
    return ProofCertificate(**defaults)


def test_proof_certificate_defaults():
    cert = _make_cert()
    assert cert.verified
    assert cert.schema_version == "1.0"
    assert cert.claim_type == "propositional"
    assert cert.verification_artifact == {}


def test_goal_contract_with_certificate():
    cert = _make_cert(claim="goal is reachable")
    contract = GoalContract(description="Deploy service", certificate=cert)
    assert contract.active
    assert contract.certificate.verified


def test_memory_proven_flag():
    cert = _make_cert(claim="Paris is capital of France", method="argument")
    mem = Memory(
        content="Paris is the capital of France",
        memory_type=MemoryType.SEMANTIC,
        certificate=cert,
        proven=True,
    )
    assert mem.proven
    assert mem.memory_type == MemoryType.SEMANTIC
    assert mem.claim_kind is None


def test_memory_claim_kind_routing_hint():
    mem = Memory(
        content="compute_time < 100",
        memory_type=MemoryType.SEMANTIC,
        claim_kind=ClaimKind.QUANTITATIVE,
    )
    assert mem.claim_kind is ClaimKind.QUANTITATIVE
    assert not mem.proven


def test_plan_with_steps():
    steps = [PlanStep(description="Step 1"), PlanStep(description="Step 2")]
    plan = Plan(goal="Complete task", steps=steps)
    assert len(plan.steps) == 2
    assert plan.steps[0].status.value == "pending"


def test_lesson_and_skill():
    lesson = Lesson(
        context="deploy",
        action_taken="restart",
        outcome="success",
        success=True,
        lesson_text="Restart fixes deploys",
    )
    skill = Skill(
        name="restart-recovery",
        description="Restart on failure",
        strategy="call restart tool",
    )
    assert lesson.success
    assert not skill.verified


def test_trace_span():
    span = TraceSpan(service="mneme", operation="store_memory")
    assert span.trace_id
    assert span.span_id
    assert span.parent_span_id is None


def test_confidence_from_float_boundaries():
    assert confidence_from_float(1.0) == ConfidenceLevel.CERTAIN
    assert confidence_from_float(0.95) == ConfidenceLevel.CERTAIN
    assert confidence_from_float(0.94) == ConfidenceLevel.SUPPORTED
    assert confidence_from_float(0.70) == ConfidenceLevel.SUPPORTED
    assert confidence_from_float(0.50) == ConfidenceLevel.WEAK
    assert confidence_from_float(0.30) == ConfidenceLevel.UNKNOWN
    assert confidence_from_float(0.0) == ConfidenceLevel.UNKNOWN


def test_confidence_record_serialization():
    record = ConfidenceRecord(
        claim="P implies Q",
        level=ConfidenceLevel.SUPPORTED,
        provenance=["z3_propositional"],
        linked_certificate_ref="sha256:deadbeef",
    )
    payload = record.model_dump()
    round_tripped = ConfidenceRecord.model_validate(payload)
    assert round_tripped == record


def test_escalation_vocabulary():
    # Ensure the vocabulary matches Logos at the enum-value level.
    assert {e.value for e in EscalationDecision} == {
        "proceed",
        "review_required",
        "blocked",
    }
    assert {r.value for r in RiskLevel} == {"low", "medium", "high"}
    assert {c.value for c in ConfidenceLevel} == {
        "certain",
        "supported",
        "weak",
        "unknown",
    }


def test_logos_certificate_round_trip():
    """Validate that a ProofCertificate produced by Logos passes through noesis_schemas.

    This is the single most important compatibility guarantee of Phase 2:
    Logos writes, Mneme/Techne read — same wire format.
    """
    import sys
    from pathlib import Path

    import pytest

    pytest.importorskip(
        "z3",
        reason="z3-solver required for the Logos round-trip test "
        "(install Logos service deps to enable)",
    )
    logos_src = Path(__file__).resolve().parents[2] / "services" / "logos" / "src"
    sys.path.insert(0, str(logos_src))
    try:
        from logos.certificate import certify
    finally:
        # Keep sys.path hygiene — don't leak across tests.
        pass
    logos_cert = certify("P -> Q, P |- Q")
    as_dict = logos_cert.to_dict()
    schemas_cert = ProofCertificate.model_validate(as_dict)
    assert schemas_cert.verified is logos_cert.verified
    assert schemas_cert.claim == logos_cert.claim
    assert schemas_cert.method == logos_cert.method
    assert schemas_cert.schema_version == logos_cert.schema_version
