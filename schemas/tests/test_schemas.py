from noesis_schemas import (
    ProofCertificate,
    GoalContract,
    Memory,
    MemoryType,
    Plan,
    PlanStep,
    Lesson,
    Skill,
    Prediction,
    TraceSpan,
)


def test_proof_certificate_defaults():
    cert = ProofCertificate(claim="P implies Q", proven=True, method="z3")
    assert cert.proven
    assert cert.certificate_id
    assert cert.confidence == 1.0


def test_goal_contract_with_certificate():
    cert = ProofCertificate(claim="goal is reachable", proven=True, method="z3")
    contract = GoalContract(description="Deploy service", certificate=cert)
    assert contract.active
    assert contract.certificate.proven


def test_memory_proven_flag():
    cert = ProofCertificate(claim="Paris is capital of France", proven=True, method="argument")
    mem = Memory(content="Paris is the capital of France", memory_type=MemoryType.SEMANTIC, certificate=cert, proven=True)
    assert mem.proven
    assert mem.memory_type == MemoryType.SEMANTIC


def test_plan_with_steps():
    steps = [PlanStep(description="Step 1"), PlanStep(description="Step 2")]
    plan = Plan(goal="Complete task", steps=steps)
    assert len(plan.steps) == 2
    assert plan.steps[0].status.value == "pending"


def test_lesson_and_skill():
    lesson = Lesson(context="deploy", action_taken="restart", outcome="success", success=True, lesson_text="Restart fixes deploys")
    skill = Skill(name="restart-recovery", description="Restart on failure", strategy="call restart tool")
    assert lesson.success
    assert not skill.verified


def test_trace_span():
    span = TraceSpan(service="mneme", operation="store_memory")
    assert span.trace_id
    assert span.span_id
    assert span.parent_span_id is None
