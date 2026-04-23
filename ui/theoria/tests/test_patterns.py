from __future__ import annotations

import pytest

from theoria.patterns import (
    EdgePredicate,
    StepPredicate,
    TraceQuery,
    parse_query,
    run_query,
)
from theoria.samples import build_samples


@pytest.fixture(scope="module")
def samples():
    return build_samples()


def test_step_predicate_on_kind_and_status(samples) -> None:
    pred = StepPredicate(kind="rule_check", status="triggered")
    matches = run_query(samples, TraceQuery(any_step=(pred,)))
    assert len(matches) == 1
    assert matches[0].id == "sample-logos-policy-block"


def test_step_predicate_label_contains_is_case_insensitive(samples) -> None:
    pred = StepPredicate(label_contains="DESTRUCTION")
    matches = run_query(samples, TraceQuery(any_step=(pred,)))
    assert any(t.id == "sample-logos-policy-block" for t in matches)


def test_step_predicate_confidence_range(samples) -> None:
    pred = StepPredicate(confidence_gte=0.8, confidence_lte=1.0)
    matches = run_query(samples, TraceQuery(any_step=(pred,)))
    assert matches  # every sample has at least one fully-confident step


def test_all_steps_requires_every_predicate_to_have_a_witness(samples) -> None:
    q = TraceQuery(all_steps=(
        StepPredicate(kind="question"),
        StepPredicate(kind="conclusion", status="failed"),
    ))
    ids = {t.id for t in run_query(samples, q)}
    # Only Logos-block and Telos-drift end in FAILED conclusions.
    assert ids == {"sample-logos-policy-block", "sample-telos-drift"}


def test_edge_predicate_on_relation(samples) -> None:
    pred = EdgePredicate(relation="contradicts")
    ids = {t.id for t in run_query(samples, TraceQuery(any_edge=(pred,)))}
    # Only the Telos drift sample has a contradicts edge.
    assert ids == {"sample-telos-drift"}


def test_query_combines_base_filter_with_predicates(samples) -> None:
    from theoria.filters import TraceFilter

    q = TraceQuery(
        base=TraceFilter(source="logos"),
        any_step=(StepPredicate(kind="conclusion", status="failed"),),
    )
    ids = [t.id for t in run_query(samples, q)]
    assert ids == ["sample-logos-policy-block"]


def test_run_query_respects_limit(samples) -> None:
    q = TraceQuery(any_step=(StepPredicate(kind="question"),))
    matches = run_query(samples, q, limit=2)
    assert len(matches) == 2


def test_parse_query_handles_mixed_fields() -> None:
    q = parse_query({
        "source": "logos",
        "tags": ["policy", "block"],
        "any_step": [{"kind": "rule_check", "label_contains": "destroy"}],
        "any_edge": [{"relation": "contradicts"}],
    })
    assert q.base.source == "logos"
    assert set(q.base.tags) == {"policy", "block"}
    assert len(q.any_step) == 1 and q.any_step[0].label_contains == "destroy"
    assert len(q.any_edge) == 1 and q.any_edge[0].relation == "contradicts"


def test_parse_query_rejects_unknown_predicate_fields() -> None:
    with pytest.raises(ValueError, match="unknown step-predicate fields"):
        parse_query({"any_step": [{"kind": "note", "bogus": 1}]})
    with pytest.raises(ValueError, match="unknown edge-predicate fields"):
        parse_query({"any_edge": [{"direction": "in"}]})


def test_parse_query_coerces_numeric_strings() -> None:
    q = parse_query({"any_step": [{"confidence_gte": "0.5"}]})
    assert q.any_step[0].confidence_gte == 0.5
