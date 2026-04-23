from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from theoria.ingest import (
    trace_from_logos_policy,
    trace_from_praxis_plan,
    trace_from_telos_drift,
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
