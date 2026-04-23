"""Integration tests against the real ``noesis_schemas`` Pydantic models.

The existing adapter unit tests use hand-rolled dataclass stand-ins to
keep Theoria dependency-free. This module is deliberately skipped when
``noesis_schemas`` isn't installed, and when it is installed it proves
the adapters work against the actual pydantic models Logos / Telos /
Praxis will send.
"""

from __future__ import annotations

import pytest

pytest.importorskip("noesis_schemas")

from noesis_schemas import (  # noqa: E402
    GoalConstraint,
    GoalContract,
    Plan,
    PlanStep,
    ProofCertificate,
    StepStatus,
    TraceSpan,
)

from theoria.ingest import (  # noqa: E402
    trace_from_goal_contract,
    trace_from_plan,
    trace_from_proof_certificate,
    trace_from_trace_spans,
)
from theoria.models import StepStatus as TheoriaStepStatus  # noqa: E402


def test_real_proof_certificate_round_trips() -> None:
    cert = ProofCertificate(
        claim_type="propositional",
        claim="x > 0 and y > 0 implies x + y > 0",
        method="z3",
        verified=True,
        timestamp="2026-04-23T14:00:00+00:00",
        verification_artifact={"status": "unsat", "solver": "z3"},
    )
    trace = trace_from_proof_certificate(cert)
    trace.validate()
    assert trace.source == "logos"
    assert trace.kind == "proof"
    assert trace.outcome is not None and trace.outcome.verdict == "verified"
    # The model's verification_artifact propagated to the evidence node.
    artifact = next(s for s in trace.steps if s.id == "artifact")
    assert artifact.meta.get("solver") == "z3"


def test_real_proof_certificate_refuted() -> None:
    cert = ProofCertificate(
        claim_type="propositional",
        claim="P implies not P",
        method="z3",
        verified=False,
        timestamp="2026-04-23T14:00:00+00:00",
    )
    trace = trace_from_proof_certificate(cert)
    assert trace.outcome is not None and trace.outcome.verdict == "refuted"
    concl = next(s for s in trace.steps if s.id == "conclusion")
    assert concl.status is TheoriaStepStatus.FAILED


def test_real_goal_contract_with_pre_and_postconditions() -> None:
    contract = GoalContract(
        description="Refactor auth module, preserve public API",
        preconditions=[
            GoalConstraint(description="public API signatures known",
                           formal="Callable[[], User]"),
        ],
        postconditions=[
            GoalConstraint(description="public API signature preserved"),
            GoalConstraint(description="tests still pass"),
        ],
    )
    trace = trace_from_goal_contract(contract)
    trace.validate()
    ids = [s.id for s in trace.steps]
    assert "pre.0" in ids and "post.0" in ids and "post.1" in ids
    assert trace.outcome is not None and trace.outcome.verdict == "active"
    pre = next(s for s in trace.steps if s.id == "pre.0")
    assert pre.detail is not None and "Callable" in pre.detail


def test_real_plan_with_mixed_statuses_fails() -> None:
    plan = Plan(
        goal="Migrate users table",
        steps=[
            PlanStep(description="dump data", tool_call="pg_dump",
                     status=StepStatus.COMPLETED, risk_score=0.1),
            PlanStep(description="alter schema",
                     status=StepStatus.FAILED, outcome="lock timeout",
                     risk_score=0.8),
        ],
    )
    trace = trace_from_plan(plan)
    trace.validate()
    assert trace.source == "praxis"
    assert trace.outcome is not None and trace.outcome.verdict == "plan-failed"
    concl = next(s for s in trace.steps if s.id == "conclusion")
    assert concl.status is TheoriaStepStatus.FAILED


def test_real_plan_empty_is_pending() -> None:
    plan = Plan(goal="Nothing to do")
    trace = trace_from_plan(plan)
    assert trace.outcome is not None and trace.outcome.verdict == "empty-plan"


def test_real_trace_spans_build_a_dag() -> None:
    spans = [
        TraceSpan(
            trace_id="t-real-1", span_id="a", parent_span_id=None,
            service="logos", operation="certify_claim",
            duration_ms=12.3, success=True, metadata={"claim_type": "propositional"},
        ),
        TraceSpan(
            trace_id="t-real-1", span_id="b", parent_span_id="a",
            service="mneme", operation="recall",
            duration_ms=4.1, success=True, metadata={"hits": "3"},
        ),
        TraceSpan(
            trace_id="t-real-1", span_id="c", parent_span_id="b",
            service="praxis", operation="commit_step",
            duration_ms=30.0, success=False, metadata={"err": "timeout"},
        ),
    ]
    trace = trace_from_trace_spans(spans)
    trace.validate()
    assert trace.source == "kairos"
    assert trace.outcome is not None and trace.outcome.verdict == "failed"
    # The metadata key/value from the real pydantic model propagates.
    b = next(s for s in trace.steps if s.id == "b")
    assert b.detail is not None and "hits=3" in b.detail


def test_real_plan_all_completed_is_ok() -> None:
    plan = Plan(
        goal="Deploy service",
        steps=[
            PlanStep(description="push image", status=StepStatus.COMPLETED, risk_score=0.1),
            PlanStep(description="run migration", status=StepStatus.COMPLETED, risk_score=0.2),
            PlanStep(description="swap traffic", status=StepStatus.COMPLETED, risk_score=0.3),
        ],
    )
    trace = trace_from_plan(plan)
    assert trace.outcome is not None and trace.outcome.verdict == "plan-ok"
