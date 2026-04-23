from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pytest

from theoria.ingest import (
    trace_from_goal_contract,
    trace_from_logos_policy,
    trace_from_plan,
    trace_from_praxis_plan,
    trace_from_proof_certificate,
    trace_from_telos_drift,
    trace_from_trace_spans,
    trace_from_tree,
)
from theoria.models import Outcome, StepStatus


class _FakeDecision(Enum):
    ALLOW = "allow"
    REVIEW_REQUIRED = "review_required"
    BLOCK = "block"


@dataclass
class _FakeViolation:
    policy_name: str
    severity: str
    message: str
    triggered_fields: list[str]
    z3_witness: dict[str, bool] | None = None


@dataclass
class _FakeResult:
    decision: _FakeDecision
    violations: list[_FakeViolation]
    remediation_hints: list[str]
    solver_status: str | None
    reason: str | None


def test_logos_block_result_produces_blocking_trace() -> None:
    result = _FakeResult(
        decision=_FakeDecision.BLOCK,
        violations=[
            _FakeViolation(
                policy_name="no_unauthorized_destruction",
                severity="error",
                message="Unauthorized destructive operation",
                triggered_fields=["destructive", "irreversible", "authorized_by_user"],
            )
        ],
        remediation_hints=["Get user authorization first"],
        solver_status="sat",
        reason=None,
    )
    trace = trace_from_logos_policy(
        result,
        action={"destructive": True, "irreversible": True, "authorized_by_user": False},
        question="May I delete /data?",
    )
    trace.validate()

    kinds = {s.id: s.kind.value for s in trace.steps}
    statuses = {s.id: s.status for s in trace.steps}

    assert kinds["q"] == "question"
    assert kinds["rule.0"] == "rule_check"
    assert statuses["rule.0"] is StepStatus.FAILED
    assert statuses["conclusion"] is StepStatus.FAILED
    assert trace.outcome is not None
    assert trace.outcome.verdict == "block"
    assert trace.source == "logos"
    assert "block" in trace.tags
    # Each action field produced an observation + an edge into the rule.
    assert any(s.id == "fact.0" for s in trace.steps)


def test_logos_allow_result_has_no_violations() -> None:
    result = _FakeResult(
        decision=_FakeDecision.ALLOW,
        violations=[],
        remediation_hints=[],
        solver_status="sat",
        reason=None,
    )
    trace = trace_from_logos_policy(result, action={"safe": True})
    assert trace.outcome is not None
    assert trace.outcome.verdict == "allow"
    concl = next(s for s in trace.steps if s.id == "conclusion")
    assert concl.status is StepStatus.OK


def test_praxis_plan_marks_selected_path_and_prunes_alternatives() -> None:
    plan_view = {
        "plan_id": "plan-abc",
        "goal": "Migrate users table",
        "nodes": {
            "s1":     {"description": "dump data",    "status": "completed",
                       "risk_score": 0.1, "score": 0.9, "tool_call": "pg_dump"},
            "s2":     {"description": "alter schema", "status": "pending",
                       "risk_score": 0.2, "score": 0.8},
            "s2_alt": {"description": "drop+recreate","status": "pending",
                       "risk_score": 0.9, "score": 0.2},
        },
        "edges": [
            ("plan-abc", "s1"),
            ("s1", "s2"),
            ("s1", "s2_alt"),
        ],
        "selected_path": ["s1", "s2"],
    }
    trace = trace_from_praxis_plan(plan_view)
    trace.validate()

    statuses = {s.id: s.status for s in trace.steps}
    assert statuses["s1"] is StepStatus.OK            # on path + completed
    assert statuses["s2"] is StepStatus.PENDING       # on path, still pending
    assert statuses["s2_alt"] is StepStatus.REJECTED  # off path → pruned

    assert trace.source == "praxis"
    assert trace.kind == "plan"
    assert trace.outcome is not None
    assert trace.outcome.verdict == "plan-selected"


def test_praxis_plan_with_no_selection_emits_pending_conclusion() -> None:
    plan_view = {
        "plan_id": "plan-xyz",
        "goal": "Explore",
        "nodes": {"s1": {"description": "think", "status": "pending"}},
        "edges": [("plan-xyz", "s1")],
    }
    trace = trace_from_praxis_plan(plan_view)
    assert trace.outcome is not None
    assert trace.outcome.verdict == "plan-pending"


@dataclass
class _FakeAlignment:
    aligned: bool
    drift_score: float
    reason: str | None


def test_telos_drift_produces_failed_conclusion_with_conflicts() -> None:
    result = _FakeAlignment(
        aligned=False,
        drift_score=0.58,
        reason="conflicts with goal 'preserve public API'",
    )
    trace = trace_from_telos_drift(
        result,
        action_description="rename authenticate() to do_auth()",
        active_goals=[
            {"goal_id": "g1", "description": "Refactor auth module, preserve public API"},
        ],
        conflicts=[
            {"goal_id": "g1", "postcondition": "public API signature preserved", "score": 0.72},
        ],
    )
    trace.validate()

    statuses = {s.id: s.status for s in trace.steps}
    assert statuses["drift"] is StepStatus.TRIGGERED
    assert statuses["conclusion"] is StepStatus.FAILED
    assert statuses["conflict.0"] is StepStatus.FAILED

    assert trace.outcome is not None
    assert trace.outcome.verdict == "drift"
    # The goal->conflict requires edge should exist (postcondition link).
    rels = {(e.source, e.target, e.relation.value) for e in trace.edges}
    assert ("goal.0", "conflict.0", "requires") in rels


def test_telos_aligned_has_ok_conclusion_without_conflicts() -> None:
    result = _FakeAlignment(aligned=True, drift_score=0.0, reason=None)
    trace = trace_from_telos_drift(
        result,
        action_description="write a unit test",
        active_goals=[{"goal_id": "g1", "description": "Improve test coverage"}],
    )
    assert trace.outcome is not None
    assert trace.outcome.verdict == "aligned"
    concl = next(s for s in trace.steps if s.id == "conclusion")
    assert concl.status is StepStatus.OK


@dataclass
class _FakeCert:
    schema_version: str
    claim_type: str
    claim: object
    method: str
    verified: bool
    timestamp: str
    verification_artifact: dict


def test_proof_certificate_verified_is_ok() -> None:
    cert = _FakeCert(
        schema_version="1.0",
        claim_type="propositional",
        claim="x > 0 and y > 0 implies x + y > 0",
        method="z3",
        verified=True,
        timestamp="2026-04-23T13:00:00+00:00",
        verification_artifact={"status": "unsat", "solver": "z3"},
    )
    trace = trace_from_proof_certificate(cert)
    trace.validate()
    concl = next(s for s in trace.steps if s.id == "conclusion")
    assert concl.status is StepStatus.OK
    assert trace.outcome is not None
    assert trace.outcome.verdict == "verified"
    # The artifact should have become an evidence node.
    assert any(s.id == "artifact" for s in trace.steps)


def test_proof_certificate_refuted_is_failed() -> None:
    cert = _FakeCert(
        schema_version="1.0",
        claim_type="propositional",
        claim="P implies not P",
        method="z3",
        verified=False,
        timestamp="2026-04-23T13:00:00+00:00",
        verification_artifact={},
    )
    trace = trace_from_proof_certificate(cert)
    assert trace.outcome is not None
    assert trace.outcome.verdict == "refuted"
    concl = next(s for s in trace.steps if s.id == "conclusion")
    assert concl.status is StepStatus.FAILED


@dataclass
class _FakeConstraint:
    description: str
    formal: str | None = None


@dataclass
class _FakeContract:
    goal_id: str
    description: str
    preconditions: list
    postconditions: list
    active: bool


def test_goal_contract_renders_each_constraint() -> None:
    contract = _FakeContract(
        goal_id="g-abc",
        description="Refactor auth module, preserve public API",
        preconditions=[
            _FakeConstraint("public API signatures known", "Callable[[], User]"),
        ],
        postconditions=[
            _FakeConstraint("public API signature preserved"),
            _FakeConstraint("tests still pass"),
        ],
        active=True,
    )
    trace = trace_from_goal_contract(contract)
    trace.validate()
    ids = [s.id for s in trace.steps]
    assert "pre.0" in ids
    assert "post.0" in ids and "post.1" in ids
    assert trace.outcome is not None
    assert trace.outcome.verdict == "active"
    # Formal expression appears in the precondition's detail.
    pre = next(s for s in trace.steps if s.id == "pre.0")
    assert pre.detail is not None and "Callable" in pre.detail


def test_inactive_goal_contract_concludes_rejected() -> None:
    contract = _FakeContract(
        goal_id="g-old", description="retired goal",
        preconditions=[], postconditions=[], active=False,
    )
    trace = trace_from_goal_contract(contract)
    concl = next(s for s in trace.steps if s.id == "conclusion")
    assert concl.status is StepStatus.REJECTED


class _PlanStatusEnum(Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class _FakePlanStep:
    step_id: str
    description: str
    tool_call: str | None
    status: object
    outcome: str | None
    risk_score: float


@dataclass
class _FakePlan:
    plan_id: str
    goal: str
    steps: list
    depth: int = 0


def test_plan_ok_when_every_step_completed() -> None:
    plan = _FakePlan(
        plan_id="p-123", goal="Migrate users",
        steps=[
            _FakePlanStep("s1", "dump data", "pg_dump", _PlanStatusEnum.COMPLETED, "ok", 0.1),
            _FakePlanStep("s2", "alter schema", None, _PlanStatusEnum.COMPLETED, "ok", 0.2),
        ],
    )
    trace = trace_from_plan(plan)
    trace.validate()
    assert trace.outcome is not None
    assert trace.outcome.verdict == "plan-ok"


def test_plan_fails_when_any_step_failed() -> None:
    plan = _FakePlan(
        plan_id="p-124", goal="Migrate users",
        steps=[
            _FakePlanStep("s1", "dump data", "pg_dump", _PlanStatusEnum.COMPLETED, "ok", 0.1),
            _FakePlanStep("s2", "alter schema", None, _PlanStatusEnum.FAILED, "lock timeout", 0.8),
        ],
    )
    trace = trace_from_plan(plan)
    assert trace.outcome is not None
    assert trace.outcome.verdict == "plan-failed"
    assert "plan-failed" in trace.tags


def test_plan_with_no_steps_is_pending() -> None:
    plan = _FakePlan(plan_id="p-empty", goal="nothing", steps=[])
    trace = trace_from_plan(plan)
    assert trace.outcome is not None
    assert trace.outcome.verdict == "empty-plan"


@dataclass
class _FakeSpan:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    service: str
    operation: str
    duration_ms: float | None
    success: bool | None
    metadata: dict


def test_trace_spans_linear_chain_all_ok() -> None:
    spans = [
        _FakeSpan("t-1", "a", None, "logos", "certify_claim", 12.3, True, {}),
        _FakeSpan("t-1", "b", "a", "mneme", "recall", 4.1, True, {"hits": "3"}),
        _FakeSpan("t-1", "c", "b", "logos", "verify_argument", 8.7, True, {}),
    ]
    trace = trace_from_trace_spans(spans)
    trace.validate()
    assert trace.source == "kairos"
    assert trace.outcome is not None and trace.outcome.verdict == "ok"
    # Parent→child edges should be YIELDS; root-level span attaches via REQUIRES.
    relations = {(e.source, e.target, e.relation.value) for e in trace.edges}
    assert ("q", "a", "requires") in relations
    assert ("a", "b", "yields") in relations
    assert ("b", "c", "yields") in relations
    # c is the only leaf; it connects to the conclusion.
    assert ("c", "conclusion", "implies") in relations


def test_trace_spans_with_failure_produces_failed_verdict() -> None:
    spans = [
        _FakeSpan("t-2", "a", None, "telos", "check_alignment", 5.0, True, {}),
        _FakeSpan("t-2", "b", "a", "praxis", "commit_step", 30.0, False, {"err": "timeout"}),
    ]
    trace = trace_from_trace_spans(spans)
    assert trace.outcome is not None and trace.outcome.verdict == "failed"
    concl = next(s for s in trace.steps if s.id == "conclusion")
    assert concl.status is StepStatus.FAILED
    # Failed span's metadata surfaces as step detail.
    b = next(s for s in trace.steps if s.id == "b")
    assert b.detail is not None and "err=timeout" in b.detail
    assert b.status is StepStatus.FAILED


def test_trace_spans_unknown_success_falls_back_to_info() -> None:
    spans = [_FakeSpan("t-3", "a", None, "custom", "noop", None, None, {})]
    trace = trace_from_trace_spans(spans)
    assert trace.outcome is not None and trace.outcome.verdict == "unknown"
    a = next(s for s in trace.steps if s.id == "a")
    assert a.status is StepStatus.INFO


def test_trace_spans_orphan_parent_attaches_to_root() -> None:
    # Parent span not included → child hangs off the synthetic root.
    spans = [
        _FakeSpan("t-4", "child", "missing-parent", "svc", "op", 1.0, True, {}),
    ]
    trace = trace_from_trace_spans(spans)
    relations = {(e.source, e.target, e.relation.value) for e in trace.edges}
    assert ("q", "child", "requires") in relations


def test_trace_spans_empty_input_raises() -> None:
    with pytest.raises(ValueError, match="at least one span"):
        trace_from_trace_spans([])


def test_trace_from_tree_walks_children() -> None:
    tree = {
        "id": "q",
        "kind": "question",
        "label": "Q",
        "children": [
            {"id": "a", "kind": "observation", "label": "A", "status": "ok"},
            {
                "id": "b",
                "kind": "inference",
                "label": "B",
                "children": [
                    {"id": "c", "kind": "conclusion", "label": "C", "status": "ok",
                     "relation": "yields"}
                ],
            },
        ],
    }
    trace = trace_from_tree(
        trace_id="tree",
        title="tree",
        question="?",
        source="custom",
        kind="custom",
        tree=tree,
        outcome=Outcome(verdict="allow", summary="ok"),
    )
    assert [s.id for s in trace.steps] == ["q", "a", "b", "c"]
    # q→a, q→b, b→c
    assert len(trace.edges) == 3
    # The child-specified relation was respected.
    c_edge = next(e for e in trace.edges if e.target == "c")
    assert c_edge.relation.value == "yields"
