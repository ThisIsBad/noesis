from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from theoria.ingest import trace_from_logos_policy, trace_from_tree
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
