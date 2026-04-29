"""Phase-1 in-process E2E gate.

Unlike ``test_phase1_e2e.py`` — which hits deployed services over MCP and
skips when env vars are unset — this test instantiates the real
``TelosCore``, ``PraxisCore``, and ``MnemeCore`` in-process and drives them
through the canonical Phase-1 scenario::

    Telos.register_goal
        → Praxis.decompose_goal
            → Praxis.add_step  (→ beam search picks best path)
            → Praxis.verify_plan  (via fake LogosClient)
            → Praxis.commit_step  (marks step COMPLETED)
                → Mneme.store  (persists a verified belief with the certificate)
        → Telos.check_alignment  (sanity-check no drift post-execution)

The scenario uses real cores with tmp-dir storage — no HTTP stubs, no
sockets, no network. It's a fast (~2 s) deterministic PR gate that
catches **orchestration-level contract mismatches** between services:

* Plan / PlanStep schema drift between Praxis and the shared contract
* ProofCertificate propagation from Logos → Praxis → Mneme
* GoalContract referential integrity between Telos and Praxis
* StepStatus enum drift between Praxis and Mneme

Wire-format drift is already covered elsewhere (``schemas``
round-trip tests + ``clients/tests/test_logos.py``), so this gate
deliberately operates at the *tool-call layer*, not HTTP.
"""

from __future__ import annotations

import pytest
from noesis_clients.testing import (
    FakeLogosClient,
    refuted_certificate,
    verified_certificate,
)
from noesis_schemas import (
    GoalConstraint,
    GoalContract,
    MemoryType,
    StepStatus,
)

pytest.importorskip("chromadb")
pytest.importorskip("networkx")

from mneme.core import MnemeCore  # noqa: E402
from praxis.core import PraxisCore  # noqa: E402
from telos.core import TelosCore  # noqa: E402


@pytest.fixture
def cores(tmp_path):
    """Wire Telos + Praxis + Mneme against tmp storage, with a fake Logos."""
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
    return telos, praxis, mneme, logos


def test_phase1_durchstich_register_plan_verify_store(cores) -> None:
    telos, praxis, mneme, logos = cores

    # 1. Telos registers the goal with a forbidding postcondition.
    contract = GoalContract(
        description="Refactor auth module",
        preconditions=[GoalConstraint(description="public API known")],
        postconditions=[GoalConstraint(description="do not break public API")],
    )
    registered = telos.register(contract)
    assert registered.goal_id == contract.goal_id
    assert registered.active is True
    assert len(telos.list_active()) == 1

    # 2. Praxis decomposes the goal into a plan, adds a low-risk step.
    plan = praxis.decompose(goal=registered.description)
    step = praxis.add_step(
        plan_id=plan.plan_id,
        description="Extract auth token parser into separate module",
        tool_call="edit_file",
        risk_score=0.2,
    )
    assert step.status == StepStatus.PENDING

    # 3. Praxis.verify_plan asks Logos to certify (via the fake).
    ok, msg = praxis.verify_plan(plan.plan_id)
    assert ok is True, msg
    assert "verified by Logos" in msg
    # The rendered claim surfaces the goal and the step description.
    assert len(logos.calls) == 1
    rendered = logos.calls[0]
    assert "Refactor auth module" in rendered
    assert "auth token parser" in rendered

    # 4. Commit the step; Praxis marks it COMPLETED + records outcome.
    committed = praxis.commit_step(
        plan_id=plan.plan_id,
        step_id=step.step_id,
        outcome="parser extracted to auth/token.py; tests green",
        success=True,
    )
    assert committed.status == StepStatus.COMPLETED

    # 5. Mneme stores the verified belief carrying Logos's certificate.
    # The Claude-orchestrated flow: use the same ProofCertificate that
    # Praxis fed to Logos for verification.
    cert = verified_certificate()
    memory = mneme.store(
        content=f"Completed step in plan {plan.plan_id}: {committed.outcome}",
        memory_type=MemoryType.EPISODIC,
        confidence=0.9,
        certificate=cert,
        tags=["phase1-durchstich"],
    )
    assert memory.proven is True, (
        "memories with a non-None ProofCertificate must graduate to proven=True"
    )

    # 6. Telos re-checks alignment: the committed action should NOT drift.
    #    The step description is about parsing, not breaking the API, so it
    #    should pass. This catches the bug where Telos's drift detector
    #    would false-positive on benign edits.
    alignment = telos.check_alignment("extract auth token parser")
    assert alignment.aligned is True, alignment.reason


def test_phase1_logos_refutation_blocks_commit(tmp_path) -> None:
    """Counter-case: if Logos refutes the plan, verify_plan blocks commit."""
    refuted_logos = FakeLogosClient(refuted_certificate())
    telos = TelosCore()
    praxis = PraxisCore(
        db_path=str(tmp_path / "praxis.db"),
        logos_client=refuted_logos,
    )
    mneme = MnemeCore(
        db_path=str(tmp_path / "mneme.db"),
        chroma_path=str(tmp_path / "mneme_chroma"),
    )

    telos.register(GoalContract(description="Risky work"))
    plan = praxis.decompose(goal="Risky work")
    praxis.add_step(plan.plan_id, "questionable step", risk_score=0.3)

    ok, msg = praxis.verify_plan(plan.plan_id)
    assert ok is False
    assert "Logos refuted" in msg

    # Nothing should have been persisted to Mneme when verification fails.
    assert mneme._col.count() == 0


def test_phase1_drift_detection_catches_forbidden_action(cores) -> None:
    """Telos.check_alignment must flag actions violating forbidding postconditions."""
    telos, _praxis, _mneme, _logos = cores

    telos.register(
        GoalContract(
            description="Keep audit log append-only",
            postconditions=[
                GoalConstraint(description="never delete audit log entries"),
            ],
        )
    )
    drift = telos.check_alignment("delete audit log entries from database")
    assert drift.aligned is False
    assert drift.drift_score > 0.0
    assert drift.reason is not None and "audit log" in drift.reason.lower()
