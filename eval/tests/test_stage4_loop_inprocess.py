"""Stage-4 full-loop in-process E2E gate.

Where ``test_phase1_inprocess.py`` exercises the Stage-3 trio
(Telos + Praxis + Mneme + a fake Logos), this test extends the loop to
cover the four remaining services so the **whole eight-service
cognitive architecture** has a deterministic regression gate that runs
in seconds without any HTTP, Railway, or docker-compose dependency::

    Episteme.log_prediction          # going-in confidence
       │
    Telos.register_goal
       └─→ Praxis.decompose_goal
             └─→ Praxis.add_step
                   └─→ Praxis.verify_plan  (fake Logos certifies)
                         └─→ Kosmos.compute_intervention  (causal lookahead)
                               └─→ Praxis.commit_step
                                     └─→ Mneme.store    (verified belief)
                                           └─→ Empiria.record  (lesson)
                                                 └─→ Techne.store  (cert-backed skill)
       │
    Episteme.log_outcome → calibration report
       │
    Telos.check_alignment            # post-execution drift check
       │
    Empiria.retrieve / Techne.retrieve  # skill+lesson reuse the next time

This test is deliberately narrow on each service's surface — deep
behaviour (do-calculus correctness, calibration math, retrieval
re-ranking) lives in each service's own unit suite. What we pin here
is **schema compatibility and orchestration order** across all eight
services, so a contract drift in any one of them fails this gate
before it reaches the live A/B harness.
"""
from __future__ import annotations

import pytest
from noesis_clients.testing import FakeLogosClient, verified_certificate
from noesis_schemas import (
    GoalConstraint,
    GoalContract,
    MemoryType,
    StepStatus,
)

pytest.importorskip("chromadb")
pytest.importorskip("networkx")

from empiria.core import EmpiriaCore  # noqa: E402
from episteme.core import EpistemeCore  # noqa: E402
from kosmos.core import KosmosCore  # noqa: E402
from mneme.core import MnemeCore  # noqa: E402
from praxis.core import PraxisCore  # noqa: E402
from techne.core import TechneCore  # noqa: E402
from telos.core import TelosCore  # noqa: E402


@pytest.fixture
def stack(tmp_path):
    """Wire every service against tmp storage with a verifying fake Logos."""
    logos = FakeLogosClient(verified_certificate())
    telos = TelosCore()
    praxis = PraxisCore(
        db_path=str(tmp_path / "praxis.db"),
        logos_client=logos,
    )
    mneme = MnemeCore(
        db_path=str(tmp_path / "mneme.db"),
        chroma_path=str(tmp_path / "mneme_chroma"),
    )
    episteme = EpistemeCore()
    kosmos = KosmosCore()
    empiria = EmpiriaCore()
    techne = TechneCore(
        db_path=str(tmp_path / "techne.db"),
        chroma_path=str(tmp_path / "techne_chroma"),
    )
    return {
        "logos": logos,
        "telos": telos,
        "praxis": praxis,
        "mneme": mneme,
        "episteme": episteme,
        "kosmos": kosmos,
        "empiria": empiria,
        "techne": techne,
    }


def test_stage4_full_loop_eight_services(stack) -> None:
    logos = stack["logos"]
    telos = stack["telos"]
    praxis = stack["praxis"]
    mneme = stack["mneme"]
    episteme = stack["episteme"]
    kosmos = stack["kosmos"]
    empiria = stack["empiria"]
    techne = stack["techne"]

    # 1. Episteme records the going-in confidence prediction.
    pred = episteme.log_prediction(
        claim="auth-refactor will land without breaking the public API",
        confidence=0.75,
        domain="refactor",
    )
    assert pred.correct is None  # not resolved yet

    # 2. Telos registers the goal with a forbidding postcondition.
    contract = GoalContract(
        description="Refactor auth module",
        preconditions=[GoalConstraint(description="public API documented")],
        postconditions=[
            GoalConstraint(description="do not break public API"),
        ],
    )
    registered = telos.register(contract)
    assert registered.active is True

    # 3. Praxis decomposes + adds a low-risk step.
    plan = praxis.decompose(goal=registered.description)
    step = praxis.add_step(
        plan_id=plan.plan_id,
        description="Extract auth token parser into separate module",
        tool_call="edit_file",
        risk_score=0.2,
    )
    assert step.status == StepStatus.PENDING

    # 4. Praxis.verify_plan asks Logos (fake) to certify the rendered claim.
    ok, msg = praxis.verify_plan(plan.plan_id)
    assert ok is True, msg
    assert len(logos.calls) == 1

    # 5. Kosmos lookahead: would this step cascade into something bad?
    #    We've encoded "extract_parser → tests_break" with a tiny weight
    #    (knowledge from past refactors). The intervention should propagate.
    kosmos.add_edge("extract_parser", "test_break_risk", strength=0.15)
    effects = kosmos.compute_intervention("extract_parser", value=1.0)
    assert "test_break_risk" in effects
    assert effects["test_break_risk"] == pytest.approx(0.15)

    # 6. Praxis commits the step (Logos verified + Kosmos blessed).
    committed = praxis.commit_step(
        plan_id=plan.plan_id,
        step_id=step.step_id,
        outcome="parser extracted to auth/token.py; tests green",
        success=True,
    )
    assert committed.status == StepStatus.COMPLETED

    # 7. Mneme persists the verified belief (carries the proof cert).
    cert = verified_certificate()
    memory = mneme.store(
        content=(
            f"Completed step in plan {plan.plan_id}: {committed.outcome}"
        ),
        memory_type=MemoryType.EPISODIC,
        confidence=0.9,
        certificate=cert,
        tags=["stage4-loop", "auth-refactor"],
    )
    assert memory.proven is True

    # 8. Empiria records the lesson — context, action, outcome.
    lesson = empiria.record(
        context="auth refactor that extracts a sub-parser",
        action_taken="edit_file: split parser out of auth/__init__.py",
        outcome=committed.outcome,
        success=True,
        lesson_text=(
            "extracting the parser before refactoring auth keeps the "
            "public API intact"
        ),
        confidence=0.8,
        domain="refactor",
    )
    assert lesson.success is True

    # 9. Techne stores the strategy as a verified skill (carrying the cert).
    skill = techne.store(
        name="extract-parser-before-auth-refactor",
        description=(
            "When refactoring auth, extract the token parser into its own "
            "module first so the diff stays inside auth/__init__.py"
        ),
        strategy=(
            "1. identify token-parsing block in auth/__init__.py\n"
            "2. cp to auth/token.py with same public symbols\n"
            "3. delete from auth/__init__.py + re-export\n"
            "4. run tests"
        ),
        certificate=cert,
        domain="refactor",
    )
    assert skill.verified is True, "cert-backed skills must round-trip verified=True"

    # 10. Episteme closes the prediction loop with the actual outcome.
    resolved = episteme.log_outcome(pred.prediction_id, correct=True)
    assert resolved.correct is True
    report = episteme.get_calibration(domain="refactor")
    assert report.sample_size == 1
    # Single-sample bias = confidence - 1 = -0.25 (we were under-confident).
    assert report.bias == pytest.approx(-0.25)

    # 11. Telos re-checks alignment post-execution; should pass.
    alignment = telos.check_alignment("extract auth token parser into a module")
    assert alignment.aligned is True, alignment.reason

    # 12. Reuse: next time a similar task comes up, retrieval surfaces both
    #     the lesson and the skill.
    lessons = empiria.retrieve(context="auth refactor")
    assert len(lessons) >= 1
    assert any("extracting the parser" in l.lesson_text for l in lessons)

    skills = techne.retrieve(query="auth refactor extract parser", k=3)
    assert len(skills) >= 1
    assert skills[0].verified is True
    assert "auth/token.py" in skills[0].strategy


def test_stage4_techne_verified_only_filter(tmp_path) -> None:
    """Cert-backed skills are visible to verified_only retrieval; bare ones aren't."""
    techne = TechneCore(
        db_path=str(tmp_path / "techne.db"),
        chroma_path=str(tmp_path / "techne_chroma"),
    )
    techne.store(
        name="verified-strategy",
        description="A strategy backed by a Logos proof",
        strategy="...",
        certificate=verified_certificate(),
    )
    techne.store(
        name="unverified-strategy",
        description="A strategy with no proof",
        strategy="...",
    )
    all_skills = techne.retrieve(query="strategy", k=5)
    verified_only = techne.retrieve(query="strategy", k=5, verified_only=True)
    assert len(all_skills) == 2
    assert len(verified_only) == 1
    assert verified_only[0].name == "verified-strategy"


def test_stage4_episteme_escalation_on_low_confidence() -> None:
    """Episteme's escalation gate fires on low going-in confidence."""
    episteme = EpistemeCore()
    # No prior calibration — should still escalate on confidence < 0.5.
    assert episteme.should_escalate(confidence=0.3) is True
    assert episteme.should_escalate(confidence=0.8) is False
